"""Tests for Point 6: Shared History, Security Controls, and Atomic Updates."""
import json
import os
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from promption.conversation import (
    ConversationStore,
    ConversationUser,
    MemoryConversationBackend,
    SQLiteConversationBackend,
    RedisConversationBackend,
    _serialize_key,
)
from promption.conversation_guard import ConversationLimitError
from promption.limiter import (
    RateLimiter,
    RedisRateLimiterBackend,
    init_rate_limiter_from_config,
    get_rate_limiter_backend,
    set_rate_limiter_backend,
)
from promption.state import (
    FileSecurityBackend,
    SQLiteSecurityBackend,
    RedisSecurityBackend,
    SecurityStateStore,
    StatePersistenceError,
)


class DummyUser:
    def __init__(self, user_id: str = "user-1", roles: list | None = None, authenticated: bool = True):
        self.id = user_id
        self.roles = roles or ["customer"]
        self.authenticated = authenticated


class MockRedisPipeline:
    def __init__(self, client):
        self.client = client
        self.watching = set()
        self.commands = []
        self.in_multi = False

    def watch(self, *keys):
        self.watching.update(keys)
        with self.client._lock:
            for k in keys:
                self.client._watch_versions[k] = self.client._versions.get(k, 0)

    def unwatch(self):
        self.watching.clear()

    def multi(self):
        self.in_multi = True

    def get(self, key):
        if self.watching and not self.in_multi:
            return self.client.get(key)
        self.commands.append(("get", (key,), {}))
        return self

    def set(self, key, val, **kwargs):
        self.commands.append(("set", (key, val), kwargs))
        return self

    def zremrangebyscore(self, key, min_s, max_s):
        self.commands.append(("zremrangebyscore", (key, min_s, max_s), {}))
        return self

    def zcard(self, key):
        self.commands.append(("zcard", (key,), {}))
        return self

    def zrange(self, key, start, stop, **kwargs):
        if self.watching and not self.in_multi:
            return self.client.zrange(key, start, stop, **kwargs)
        self.commands.append(("zrange", (key, start, stop), kwargs))
        return self

    def zadd(self, key, mapping):
        self.commands.append(("zadd", (key, mapping), {}))
        return self

    def expire(self, key, ttl):
        self.commands.append(("expire", (key, ttl), {}))
        return self

    def delete(self, *keys):
        self.commands.append(("delete", keys, {}))
        return self

    def zrem(self, key, *members):
        self.commands.append(("zrem", (key, *members), {}))
        return self

    def execute(self):
        with self.client._lock:
            # Check version collisions on watched keys
            for k in self.watching:
                if self.client._watch_versions.get(k, 0) != self.client._versions.get(k, 0):
                    raise RuntimeError("WatchError: Key changed")
            res = []
            for cmd, args, kwargs in self.commands:
                method = getattr(self.client, cmd)
                res.append(method(*args, **kwargs))
            self.commands.clear()
            self.in_multi = False
            self.watching.clear()
            return res

    def reset(self):
        self.commands.clear()
        self.in_multi = False
        self.watching.clear()


class ControlledMockRedis:
    """In-memory Redis mock supporting atomic pipelines, watch, Lua eval, and sorted sets."""

    def __init__(self):
        self._data = {}
        self._versions = {}
        self._watch_versions = {}
        self._expires = {}
        self._lock = threading.RLock()

    def pipeline(self):
        return MockRedisPipeline(self)

    def get(self, key):
        with self._lock:
            return self._data.get(key)

    def set(self, key, val, ex=None, **kwargs):
        with self._lock:
            self._data[key] = val
            self._versions[key] = self._versions.get(key, 0) + 1
            if ex is not None:
                self._expires[key] = time.time() + float(ex)
            else:
                self._expires.pop(key, None)
            return True

    def delete(self, *keys):
        with self._lock:
            for k in keys:
                self._data.pop(k, None)
                self._expires.pop(k, None)
                self._versions[k] = self._versions.get(k, 0) + 1

    def keys(self, pattern):
        with self._lock:
            prefix = pattern.rstrip("*")
            return [k for k in self._data if k.startswith(prefix)]

    def zremrangebyscore(self, key, min_s, max_s):
        with self._lock:
            zset = self._data.get(key, {})
            max_val = float("inf") if max_s == "+inf" else float(max_s)
            min_val = float("-inf") if min_s == "-inf" else float(min_s)
            removed = [m for m, score in zset.items() if min_val <= score <= max_val]
            for m in removed:
                del zset[m]
            return len(removed)

    def zcard(self, key):
        with self._lock:
            return len(self._data.get(key, {}))

    def zrange(self, key, start, stop, withscores=False):
        with self._lock:
            zset = self._data.get(key, {})
            sorted_items = sorted(zset.items(), key=lambda x: x[1])
            items = sorted_items[start : stop + 1 if stop != -1 else None]
            if withscores:
                return items
            return [item[0] for item in items]

    def zadd(self, key, mapping):
        with self._lock:
            zset = self._data.setdefault(key, {})
            for m, score in mapping.items():
                zset[m] = float(score)
            return len(mapping)

    def expire(self, key, ttl):
        with self._lock:
            if key in self._data:
                self._expires[key] = time.time() + float(ttl)
                return True
            return False

    def ttl(self, key):
        with self._lock:
            if key not in self._data:
                return -2
            if key not in self._expires:
                return -1
            rem = int(self._expires[key] - time.time())
            return max(0, rem)

    def zrem(self, key, *members):
        with self._lock:
            zset = self._data.get(key, {})
            count = 0
            for m in members:
                if m in zset:
                    del zset[m]
                    count += 1
            return count

    def zscore(self, key, member):
        with self._lock:
            zset = self._data.get(key, {})
            return zset.get(member)

    def eval(self, script, numkeys, *args):
        with self._lock:
            if "conv:_index" in str(script) or (len(args) > 0 and args[0] == "conv:_index"):
                index_key = args[0]
                current_key = str(args[1])
                now_ts = float(args[2])
                max_conv = int(args[3])
                if now_ts > 0:
                    self.zadd(index_key, {current_key: now_ts})
                total = self.zcard(index_key)
                if total > max_conv:
                    excess = total - max_conv
                    oldest = self.zrange(index_key, 0, excess - 1)
                    for k in oldest:
                        k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                        if k_str != current_key:
                            self.delete(k_str)
                            self.zrem(index_key, k_str)
                return total

            key = args[0]
            now = float(args[1])
            window = float(args[2])
            limit = int(args[3])
            cost = int(args[4])
            token_prefix = str(args[5])

            cutoff = now - window
            self.zremrangebyscore(key, "-inf", cutoff)
            current = self.zcard(key)

            if current + cost > limit:
                oldest_list = self.zrange(key, 0, 0, withscores=True)
                oldest_ts = oldest_list[0][1] if oldest_list else now
                retry_after = max(1, int(oldest_ts + window - now))
                return [0, retry_after]

            for i in range(1, cost + 1):
                self.zadd(key, {f"{token_prefix}_{i}": now})
            self.expire(key, int(window) + 5)
            self._versions[key] = self._versions.get(key, 0) + 1
            return [1, 0]


# ----------------------------------------------------------------------
# 1. Two Instances Share History, Controls, and Quotas
# ----------------------------------------------------------------------
def test_two_instances_share_conversation_history_sqlite(tmp_path):
    db_file = tmp_path / "shared_conv.db"
    store_1 = ConversationStore(tenant_id="tenant_x", backend=SQLiteConversationBackend(db_file))
    store_2 = ConversationStore(tenant_id="tenant_x", backend=SQLiteConversationBackend(db_file))

    user = DummyUser("user-100")
    conv_id = str(uuid.uuid4())

    # Instance 1 records a turn
    store_1.record(conv_id, user, "¿Cuál es el horario?", "Atendemos de 9 a 18.", "publico", [])

    # Instance 2 reads snapshot and display
    messages, protected = store_2.snapshot(conv_id, user)
    assert len(messages) == 2
    assert messages[0]["content"] == "¿Cuál es el horario?"
    assert messages[1]["content"] == "Atendemos de 9 a 18."
    assert protected is False

    visible = store_2.display(conv_id, user)
    assert len(visible) == 2
    assert visible[0]["text"] == "¿Cuál es el horario?"
    assert visible[1]["text"] == "Atendemos de 9 a 18."

    # Instance 2 appends security evidence
    store_2.append_security(conv_id, user, [{"role": "user", "content": "Security check fragment"}])

    # Instance 1 sees the updated security snapshot
    sec_evidence = store_1.security_snapshot(conv_id, user)
    assert any("Security check fragment" in m["content"] for m in sec_evidence)


def test_two_instances_share_conversation_history_redis():
    mock_redis = ControlledMockRedis()
    store_1 = ConversationStore(tenant_id="tenant_y", backend=RedisConversationBackend(mock_redis))
    store_2 = ConversationStore(tenant_id="tenant_y", backend=RedisConversationBackend(mock_redis))

    user = DummyUser("user-200")
    conv_id = str(uuid.uuid4())

    store_1.record(conv_id, user, "Hola tienda", "Bienvenido", "publico", [])
    messages, _ = store_2.snapshot(conv_id, user)
    assert len(messages) == 2
    assert messages[0]["content"] == "Hola tienda"


def test_two_instances_share_security_controls(tmp_path):
    state_file = tmp_path / "security_state.json"
    store_1 = SecurityStateStore(str(state_file))
    store_2 = SecurityStateStore(str(state_file))

    # Instance 1 disables output guard
    store_1.update("output_guard", False, "admin@test.org")

    # Instance 2 reflects the change and incremented version
    state_2 = store_2.get()
    assert state_2["output_guard_enabled"] is False
    assert state_2["version"] == 2
    assert state_2["updated_by"] == "admin@test.org"
    assert len(state_2["history"]) == 1


def test_two_instances_share_redis_rate_limiting_quotas():
    mock_redis = ControlledMockRedis()
    backend_1 = RedisRateLimiterBackend(mock_redis)
    backend_2 = RedisRateLimiterBackend(mock_redis)

    limiter_1 = RateLimiter(backend=backend_1)
    limiter_2 = RateLimiter(backend=backend_2)

    tenant_id = "tenant_shared_quota"
    quotas = {"requests_per_minute": 3}

    # Consume 2 requests via instance 1
    limiter_1.check_protection_quota(tenant_id, tenant_quotas=quotas)
    limiter_1.check_protection_quota(tenant_id, tenant_quotas=quotas)

    # Consume 1 request via instance 2 (reaches limit 3)
    limiter_2.check_protection_quota(tenant_id, tenant_quotas=quotas)

    # 4th request on instance 1 is blocked with HTTP 429
    with pytest.raises(Exception) as exc_info:
        limiter_1.check_protection_quota(tenant_id, tenant_quotas=quotas)
    assert exc_info.value.status_code == 429


# ----------------------------------------------------------------------
# 2. Concurrent Updates Are Not Lost (No Blind Overwrite)
# ----------------------------------------------------------------------
def test_concurrent_security_appends_are_not_lost(tmp_path):
    db_file = tmp_path / "concurrent_conv.db"
    store = ConversationStore(tenant_id="tenant_conc", backend=SQLiteConversationBackend(db_file))

    user = DummyUser("user-concurrent")
    conv_id = str(uuid.uuid4())

    num_threads = 8
    barrier = threading.Barrier(num_threads)

    def worker(i):
        barrier.wait()
        store.append_security(conv_id, user, [{"role": "user", "content": f"msg-{i}"}])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    evidence = store.security_snapshot(conv_id, user)
    contents = {m["content"] for m in evidence}
    assert len(contents) == num_threads
    for i in range(num_threads):
        assert f"msg-{i}" in contents


# ----------------------------------------------------------------------
# 3. Isolation & TTL
# ----------------------------------------------------------------------
def test_strict_isolation_across_tenants_users_roles(tmp_path):
    db_file = tmp_path / "iso_conv.db"
    store_a = ConversationStore(tenant_id="tenant_alpha", backend=SQLiteConversationBackend(db_file))
    store_b = ConversationStore(tenant_id="tenant_beta", backend=SQLiteConversationBackend(db_file))

    conv_id = str(uuid.uuid4())
    user_1 = DummyUser("user-1", roles=["customer"])
    user_2 = DummyUser("user-2", roles=["customer"])
    user_1_admin = DummyUser("user-1", roles=["admin"])

    store_a.record(conv_id, user_1, "Secret alpha", "Resp alpha", "interno", [])

    # 1. Tenant B cannot see Tenant A's conversation
    msg_b, _ = store_b.snapshot(conv_id, user_1)
    assert msg_b == []

    # 2. User 2 cannot see User 1's conversation
    msg_u2, _ = store_a.snapshot(conv_id, user_2)
    assert msg_u2 == []

    # 3. Different roles cannot see each other's conversation
    msg_admin, _ = store_a.snapshot(conv_id, user_1_admin)
    assert msg_admin == []


def test_ttl_expiration_prunes_conversation(tmp_path):
    db_file = tmp_path / "ttl_conv.db"
    backend = SQLiteConversationBackend(db_file)
    store = ConversationStore(tenant_id="tenant_ttl", ttl_seconds=1, backend=backend)

    user = DummyUser("user-ttl")
    conv_id = str(uuid.uuid4())

    store.record(conv_id, user, "Hello", "World", "publico", [])
    assert len(store.snapshot(conv_id, user)[0]) == 2

    # Simulate passage of time beyond TTL
    time.sleep(1.1)

    # After TTL, conversation is pruned
    assert store.snapshot(conv_id, user)[0] == []
    assert store.security_snapshot(conv_id, user) == []


# ----------------------------------------------------------------------
# 4. Atomic File Replacement and Persistence Error Handling
# ----------------------------------------------------------------------
def test_security_state_atomic_replace_and_temp_file_cleanup(tmp_path):
    state_file = tmp_path / "security_state.json"
    backend = FileSecurityBackend(state_file)

    backend.update_state("filter", False, "admin@test.org")
    assert state_file.exists()

    # Verify no dangling temp files remain in directory
    temp_files = list(tmp_path.glob(".tmp_*"))
    assert len(temp_files) == 0


def test_security_state_persistence_failure_raises_and_not_returned_as_success(tmp_path, monkeypatch):
    state_file = tmp_path / "security_state.json"
    store = SecurityStateStore(str(state_file))

    # Mock os.replace to simulate I/O or permissions failure
    def failing_replace(src, dst):
        raise OSError("Permission denied: disk read-only")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(StatePersistenceError) as exc_info:
        store.update("filter", False, "admin@test.org")

    assert "Failed to atomically persist security state" in str(exc_info.value)

    # State file must not have been created or corrupted
    assert not state_file.exists()


def test_security_state_optimistic_concurrency_version_conflict(tmp_path):
    state_file = tmp_path / "version_test.json"
    store = SecurityStateStore(str(state_file))

    s1 = store.get()
    assert s1["version"] == 1

    # Update with expected_version = 1 succeeds
    store.update("filter", False, "admin@test.org", expected_version=1)

    # Update with stale expected_version = 1 must fail with StatePersistenceError!
    with pytest.raises(StatePersistenceError) as exc_info:
        store.update("filter", True, "admin@test.org", expected_version=1)
    assert "Version conflict" in str(exc_info.value)


# ----------------------------------------------------------------------
# 5. Restart, Recovery & Safe Fallback
# ----------------------------------------------------------------------
def test_corrupted_security_state_falls_back_to_safe_defaults(tmp_path):
    state_file = tmp_path / "corrupted_state.json"
    state_file.write_text("{{invalid json content!@@", encoding="utf-8")

    store = SecurityStateStore(str(state_file))
    state = store.get()

    # Fail safe: must enable all protections by default
    assert state["filter_enabled"] is True
    assert state["output_guard_enabled"] is True
    assert state["version"] == 1


# ----------------------------------------------------------------------
# 6. Missing / Unavailable Security Evidence Fails Closed
# ----------------------------------------------------------------------
def test_missing_or_corrupted_security_evidence_fails_closed(tmp_path):
    db_file = tmp_path / "evidence_loss.db"
    backend = SQLiteConversationBackend(db_file)
    store = ConversationStore(tenant_id="tenant_loss", backend=backend)

    user = DummyUser("user-loss")
    conv_id = str(uuid.uuid4())

    store.record(conv_id, user, "User prompt", "Assistant answer", "publico", [])

    # Simulate evidence loss or corruption in storage while turns exist
    str_key = store._key(conv_id, user)
    item = backend.get(str_key)
    item["security"] = []  # Evidence wiped/lost!
    item["security_lost"] = True

    # Save corrupted item back
    with backend._lock, backend._get_connection() as conn:
        import json
        conn.execute("UPDATE conversations SET data_json = ? WHERE key = ?", (json.dumps(item), _serialize_key(str_key)))

    # When security evidence is unavailable, must NOT silently continue with partial history!
    with pytest.raises(ConversationLimitError) as exc_info:
        store.security_snapshot(conv_id, user)
    assert "Security evidence is unavailable" in str(exc_info.value)


# ----------------------------------------------------------------------
# 7. Multi-Worker Validation in Chat Service
# ----------------------------------------------------------------------
def test_multi_worker_rejects_in_memory_backend(monkeypatch):
    import sys
    chat_dir = Path(__file__).resolve().parents[1] / "chat-service"
    if str(chat_dir) not in sys.path:
        sys.path.insert(0, str(chat_dir))
    from app.conversation import create_conversation_backend

    monkeypatch.setenv("CHAT_SERVICE_WORKERS", "4")
    monkeypatch.setenv("PROMPTION_STORAGE_BACKEND", "memory")

    with pytest.raises(ValueError) as exc_info:
        create_conversation_backend()
    assert "in-memory conversation store cannot be used with multiple workers" in str(exc_info.value)


# ----------------------------------------------------------------------
# 8. Strict Atomic Redis Rate Limiting (Single Transaction / Lua)
# ----------------------------------------------------------------------
def test_redis_rate_limit_strictly_atomic_limit_one():
    mock_redis = ControlledMockRedis()
    backend = RedisRateLimiterBackend(mock_redis)

    num_threads = 4
    results = []
    barrier = threading.Barrier(num_threads)

    def worker():
        barrier.wait()
        allowed, retry_after = backend.check_and_consume("atomic_user", limit=1, window_seconds=60, cost=1)
        results.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # With limit 1, EXACTLY ONE request must be allowed, and all others rejected!
    assert results.count(True) == 1, f"Expected exactly 1 allowed, got {results.count(True)}"
    assert results.count(False) == num_threads - 1


def test_redis_rate_limit_strictly_atomic_cas_fallback():
    # Test fallback path when eval is not available
    mock_redis = ControlledMockRedis()
    mock_redis.eval = None  # disable eval to force CAS transaction
    backend = RedisRateLimiterBackend(mock_redis)

    num_threads = 4
    results = []
    barrier = threading.Barrier(num_threads)

    def worker():
        barrier.wait()
        allowed, retry_after = backend.check_and_consume("atomic_cas_user", limit=1, window_seconds=60, cost=1)
        results.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1, f"Expected exactly 1 allowed in CAS fallback, got {results.count(True)}"
    assert results.count(False) == num_threads - 1


# ----------------------------------------------------------------------
# 9. Rate Limiter Startup Configuration Binding
# ----------------------------------------------------------------------
def test_rate_limiter_initialized_from_config_or_env(monkeypatch):
    old_backend = get_rate_limiter_backend()
    try:
        # 1. Default or 'memory' initializes MemoryRateLimiterBackend
        monkeypatch.setenv("PROMPTION_RATE_LIMITER_BACKEND", "memory")
        b_mem = init_rate_limiter_from_config()
        assert b_mem.__class__.__name__ == "MemoryRateLimiterBackend"
        assert get_rate_limiter_backend() is b_mem

        # 2. 'redis' initializes RedisRateLimiterBackend
        monkeypatch.setenv("PROMPTION_RATE_LIMITER_BACKEND", "redis")
        mock_client = ControlledMockRedis()
        import redis
        monkeypatch.setattr(redis, "from_url", lambda url: mock_client)

        b_redis = init_rate_limiter_from_config()
        assert isinstance(b_redis, RedisRateLimiterBackend)
        assert get_rate_limiter_backend() is b_redis

        # 3. Global routes RateLimiter picks up the active backend dynamically
        r_limiter = RateLimiter()
        assert isinstance(r_limiter.backend, RedisRateLimiterBackend)
    finally:
        set_rate_limiter_backend(old_backend)


# ----------------------------------------------------------------------
# 10. Security Controls Cross-Instance Optimistic Concurrency
# ----------------------------------------------------------------------
def test_security_controls_cross_instance_version_conflict_sqlite(tmp_path):
    db_file = tmp_path / "sec_controls.db"
    store_1 = SecurityStateStore(str(db_file), backend=SQLiteSecurityBackend(db_file))
    store_2 = SecurityStateStore(str(db_file), backend=SQLiteSecurityBackend(db_file))

    s1 = store_1.get()
    assert s1["version"] == 1

    # Instance 1 updates with expected_version=1 -> version 2
    store_1.update("filter", False, "admin1@test.org", expected_version=1)
    assert store_1.get()["version"] == 2

    # Instance 2 tries to update with stale expected_version=1 -> MUST fail!
    with pytest.raises(StatePersistenceError) as exc_info:
        store_2.update("output_guard", False, "admin2@test.org", expected_version=1)
    assert "Version conflict" in str(exc_info.value)

    # Valid update with expected_version=2 succeeds
    store_2.update("output_guard", False, "admin2@test.org", expected_version=2)
    s2 = store_2.get()
    assert s2["version"] == 3
    assert len(s2["history"]) == 2


def test_security_controls_cross_instance_version_conflict_file_json(tmp_path):
    json_file = tmp_path / "sec_controls.json"
    store_1 = SecurityStateStore(str(json_file), backend=FileSecurityBackend(json_file))
    store_2 = SecurityStateStore(str(json_file), backend=FileSecurityBackend(json_file))

    s1 = store_1.get()
    assert s1["version"] == 1

    # Instance 1 updates with expected_version=1
    store_1.update("filter", False, "admin1@test.org", expected_version=1)
    assert store_1.get()["version"] == 2

    # Instance 2 tries to update with expected_version=1 -> MUST fail!
    with pytest.raises(StatePersistenceError) as exc_info:
        store_2.update("output_guard", False, "admin2@test.org", expected_version=1)
    assert "Version conflict" in str(exc_info.value)

    # Valid update with expected_version=2 succeeds
    store_2.update("output_guard", False, "admin2@test.org", expected_version=2)
    s2 = store_2.get()
    assert s2["version"] == 3
    assert len(s2["history"]) == 2


# ----------------------------------------------------------------------
# 11. Missing File Always Safe Defaults & Memory Update Only After Persist
# ----------------------------------------------------------------------
def test_missing_file_returns_safe_defaults_even_after_in_memory_mutation(tmp_path):
    json_file = tmp_path / "controls.json"
    store = SecurityStateStore(str(json_file), backend=FileSecurityBackend(json_file))

    # Disable filter
    store.update("filter", False, "admin@test.org")
    assert store.get()["filter_enabled"] is False

    # Delete the underlying file
    json_file.unlink()
    assert not json_file.exists()

    # get() MUST return safe defaults (True), never stale in-memory False!
    safe_state = store.get()
    assert safe_state["filter_enabled"] is True
    assert safe_state["output_guard_enabled"] is True
    assert safe_state["version"] == 1


def test_write_failure_does_not_update_in_memory_state(tmp_path, monkeypatch):
    json_file = tmp_path / "failing_controls.json"
    backend = FileSecurityBackend(json_file)

    initial_memory = dict(backend._memory)

    def failing_replace(src, dst):
        raise OSError("Simulated atomic replace disk write error")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(StatePersistenceError):
        backend.update_state("filter", False, "admin@test.org")

    # In-memory state must NOT have been updated
    assert backend._memory["filter_enabled"] == initial_memory["filter_enabled"]
    assert backend._memory["version"] == initial_memory["version"]


# ----------------------------------------------------------------------
# 12. Conversation Key Serialization Prevents Delimiter Collision
# ----------------------------------------------------------------------
def test_conversation_key_no_delimiter_collision():
    key_1 = ("tenant", "a:b", ["c"], True, "conv-1")
    key_2 = ("tenant", "a", ["b:c"], True, "conv-1")

    # The serialized keys MUST be distinct
    serialized_1 = _serialize_key(key_1)
    serialized_2 = _serialize_key(key_2)
    assert serialized_1 != serialized_2

    # Verify across backends
    # 1. Memory backend
    conv_id = str(uuid.uuid4())
    mem_backend = MemoryConversationBackend()
    user_1 = DummyUser("a:b", roles=["c"])
    user_2 = DummyUser("a", roles=["b:c"])
    store_mem = ConversationStore(tenant_id="tenant", backend=mem_backend)
    store_mem.record(conv_id, user_1, "Prompt 1", "Resp 1", "publico", [])

    assert len(store_mem.snapshot(conv_id, user_1)[0]) == 2
    assert len(store_mem.snapshot(conv_id, user_2)[0]) == 0

    # 2. Redis backend
    mock_redis = ControlledMockRedis()
    store_redis = ConversationStore(tenant_id="tenant", backend=RedisConversationBackend(mock_redis))
    store_redis.record(conv_id, user_1, "Prompt 1", "Resp 1", "publico", [])

    assert len(store_redis.snapshot(conv_id, user_1)[0]) == 2
    assert len(store_redis.snapshot(conv_id, user_2)[0]) == 0


# ----------------------------------------------------------------------
# 13. Redis mark_security_overflow() is Atomic and Preserves TTL
# ----------------------------------------------------------------------
def test_redis_mark_security_overflow_atomic_preserves_ttl():
    mock_redis = ControlledMockRedis()
    backend = RedisConversationBackend(mock_redis)
    store = ConversationStore(tenant_id="tenant_ttl_test", ttl_seconds=3600, backend=backend)

    user = DummyUser("user_overflow")
    conv_id = str(uuid.uuid4())

    # Record turn with evidence and 3600s TTL
    store.record(conv_id, user, "Prompt check", "Reply check", "publico", [])
    store.append_security(conv_id, user, [{"role": "user", "content": "Important evidence"}])

    key = store._key(conv_id, user)
    str_key = _serialize_key(key)

    # Check that TTL is around 3600s
    ttl_before = mock_redis.ttl(str_key)
    assert ttl_before > 3500

    # Advance time slightly
    mock_redis._expires[str_key] = time.time() + 2500

    # Call mark_security_overflow
    backend.mark_security_overflow(key)

    # Key must still exist, overflow flag set, evidence retained, and TTL preserved
    item = json.loads(mock_redis.get(str_key))
    assert item["security_overflow"] is True
    assert len(item["security"]) == 2
    assert any(m["content"] == "Important evidence" for m in item["security"])

    ttl_after = mock_redis.ttl(str_key)
    assert 2400 < ttl_after <= 2500, f"Expected TTL to be preserved around 2500, got {ttl_after}"


# ----------------------------------------------------------------------
# 14. RedisSecurityBackend Lifecycle, Atomic Versioning & Safe Defaults
# ----------------------------------------------------------------------
def test_redis_security_backend_comprehensive():
    mock_redis = ControlledMockRedis()
    backend_1 = RedisSecurityBackend(mock_redis, key="sec:shared_state")
    backend_2 = RedisSecurityBackend(mock_redis, key="sec:shared_state")

    store_1 = SecurityStateStore("dummy.json", backend=backend_1)
    store_2 = SecurityStateStore("dummy.json", backend=backend_2)

    # Safe defaults on empty key
    state_init = store_1.get()
    assert state_init["filter_enabled"] is True
    assert state_init["output_guard_enabled"] is True
    assert state_init["version"] == 1

    # Instance 1 updates with expected_version=1 -> version 2
    store_1.update("filter", False, "admin@test.org", expected_version=1)
    s1 = store_1.get()
    assert s1["filter_enabled"] is False
    assert s1["version"] == 2
    assert s1["updated_by"] == "admin@test.org"

    # Instance 2 reflects the update
    s2 = store_2.get()
    assert s2["filter_enabled"] is False
    assert s2["version"] == 2

    # Stale version update from instance 2 must fail with StatePersistenceError
    with pytest.raises(StatePersistenceError) as exc_info:
        store_2.update("output_guard", False, "attacker@test.org", expected_version=1)
    assert "Version conflict" in str(exc_info.value)

    # Valid update with expected_version=2 succeeds
    store_2.update("output_guard", False, "admin2@test.org", expected_version=2)
    s2_updated = store_2.get()
    assert s2_updated["output_guard_enabled"] is False
    assert s2_updated["version"] == 3
    assert len(s2_updated["history"]) == 2

    # Corrupted Redis content returns safe defaults
    mock_redis.set("sec:shared_state", "{invalid:json:content")
    corrupt_state = store_1.get()
    assert corrupt_state["filter_enabled"] is True
    assert corrupt_state["output_guard_enabled"] is True
    assert corrupt_state["version"] == 1


# ----------------------------------------------------------------------
# 15. Chat Service Storage Backend Multi-Worker Enforcement
# ----------------------------------------------------------------------
def test_chat_service_security_state_rejects_multi_worker_file_and_accepts_sqlite(monkeypatch):
    import sys
    chat_dir = Path(__file__).resolve().parents[1] / "chat-service"
    if str(chat_dir) not in sys.path:
        sys.path.insert(0, str(chat_dir))
    from app.security_state import _create_security_store

    # 1. Multiple workers with file backend raises ValueError
    monkeypatch.setenv("CHAT_SERVICE_WORKERS", "2")
    monkeypatch.setenv("PROMPTION_STORAGE_BACKEND", "file")
    with pytest.raises(ValueError) as exc_info:
        _create_security_store()
    assert "JSON/file security controls cannot be used with multiple workers" in str(exc_info.value)

    # 2. SQLite backend creates SQLiteSecurityBackend
    monkeypatch.setenv("CHAT_SERVICE_WORKERS", "2")
    monkeypatch.setenv("PROMPTION_STORAGE_BACKEND", "sqlite")
    store = _create_security_store()
    assert isinstance(store.backend, SQLiteSecurityBackend)



# ----------------------------------------------------------------------
# 16. Redis max_conversations Pruning
# ----------------------------------------------------------------------
def test_redis_enforces_max_conversations():
    mock_redis = ControlledMockRedis()
    backend = RedisConversationBackend(mock_redis, max_conversations=1)
    store = ConversationStore(tenant_id="tenant_max_conv", max_conversations=1, backend=backend)

    user = DummyUser("user_max")
    c1 = str(uuid.uuid4())
    c2 = str(uuid.uuid4())
    c3 = str(uuid.uuid4())

    store.record(c1, user, "Q1", "A1", "publico", [])
    store.record(c2, user, "Q2", "A2", "publico", [])
    store.record(c3, user, "Q3", "A3", "publico", [])

    # With max_conversations=1, only c3 must remain; c1 and c2 pruned!
    assert len(store.snapshot(c1, user)[0]) == 0
    assert len(store.snapshot(c2, user)[0]) == 0
    assert len(store.snapshot(c3, user)[0]) == 2


def test_redis_enforces_max_conversations_fallback():
    mock_redis = ControlledMockRedis()
    mock_redis.eval = None
    backend = RedisConversationBackend(mock_redis, max_conversations=1)
    store = ConversationStore(tenant_id="tenant_max_conv_fb", max_conversations=1, backend=backend)

    user = DummyUser("user_max_fb")
    c1 = str(uuid.uuid4())
    c2 = str(uuid.uuid4())

    store.record(c1, user, "Q1", "A1", "publico", [])
    store.record(c2, user, "Q2", "A2", "publico", [])

    # With max_conversations=1 in fallback, only c2 must remain!
    assert len(store.snapshot(c1, user)[0]) == 0
    assert len(store.snapshot(c2, user)[0]) == 2


# ----------------------------------------------------------------------
# 17. Stale Process Lock Recovery
# ----------------------------------------------------------------------
def test_stale_process_file_lock_recovery(tmp_path):
    lock_file = tmp_path / "test.lock"
    # Create an abandoned lock file simulating a crashed process
    lock_file.write_text("99999999:1000.0", encoding="utf-8")
    # Set mtime to 10 seconds ago
    old_time = time.time() - 10.0
    os.utime(lock_file, (old_time, old_time))

    from promption.state import _ProcessFileLock
    # Must recover the stale lock and succeed, not time out
    lock = _ProcessFileLock(lock_file, timeout=2.0, stale_seconds=1.0)
    with lock:
        assert lock_file.exists()


def test_active_process_lock_is_not_stolen_by_age(tmp_path):
    lock_file = tmp_path / "active.lock"
    # Create lock file with current process's PID (which is alive!)
    lock_file.write_text(f"{os.getpid()}:{time.time()}", encoding="utf-8")
    old_time = time.time() - 100.0
    os.utime(lock_file, (old_time, old_time))

    from promption.state import _ProcessFileLock, StatePersistenceError
    lock = _ProcessFileLock(lock_file, timeout=0.1, stale_seconds=1.0)
    with pytest.raises(StatePersistenceError):
        with lock:
            pass
    # Lock file must still exist and NOT have been deleted
    assert lock_file.exists()


def test_stale_lock_recovery_does_not_unlink_new_owner(tmp_path, monkeypatch):
    lock_file = tmp_path / "race.lock"
    lock_file.write_text("99999999:1000.0", encoding="utf-8")
    old_time = time.time() - 10.0
    os.utime(lock_file, (old_time, old_time))

    from promption.state import _ProcessFileLock
    lock = _ProcessFileLock(lock_file, timeout=0.1, stale_seconds=1.0)

    # Simulate another process replacing the lock right after first check
    original_read_text = Path.read_text
    reads = 0
    def mock_read_text(self_path, *args, **kwargs):
        nonlocal reads
        reads += 1
        if self_path == lock_file:
            if reads == 1:
                return "99999999:1000.0"
            else:
                return f"{os.getpid()}:{time.time()}"
        return original_read_text(self_path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    lock._recover_stale_lock()
    # Must NOT unlink the new owner's active lock
    assert lock_file.exists()


def test_corrupt_pid_in_lock_does_not_raise_value_error_and_recovers(tmp_path):
    lock_file = tmp_path / "corrupt_pid.lock"
    # Content has non-integer PID string
    lock_file.write_text("corrupted_pid_string:1000.0", encoding="utf-8")
    old_time = time.time() - 10.0
    os.utime(lock_file, (old_time, old_time))

    from promption.state import _ProcessFileLock
    lock = _ProcessFileLock(lock_file, timeout=2.0, stale_seconds=1.0)
    # Must not raise ValueError and must recover the lock
    with lock:
        assert lock_file.exists()


def test_recovery_lock_mutex_prevents_simultaneous_recovery(tmp_path):
    lock_file = tmp_path / "stale_main.lock"
    lock_file.write_text("99999999:1000.0", encoding="utf-8")
    old_time = time.time() - 10.0
    os.utime(lock_file, (old_time, old_time))

    rec_lock = lock_file.with_suffix(".recover")
    # Simulate an active recovery lock held by another process
    rec_lock.write_text("recovering", encoding="utf-8")

    from promption.state import _ProcessFileLock
    lock = _ProcessFileLock(lock_file, timeout=0.1, stale_seconds=1.0)
    # Should safely return without touching stale_main.lock because rec_lock is held
    lock._recover_stale_lock()
    assert lock_file.exists()
    assert rec_lock.exists()


def test_recovery_lock_mutex_not_unlinked_while_owner_alive(tmp_path):
    lock_file = tmp_path / "stale_main2.lock"
    lock_file.write_text("99999999:1000.0", encoding="utf-8")
    old_time = time.time() - 100.0
    os.utime(lock_file, (old_time, old_time))

    rec_lock = lock_file.with_suffix(".recover")
    # Write current process PID (which is alive!) with old timestamp
    rec_lock.write_text(f"{os.getpid()}:{time.time()}", encoding="utf-8")
    os.utime(rec_lock, (old_time, old_time))

    from promption.state import _ProcessFileLock
    lock = _ProcessFileLock(lock_file, timeout=0.1, stale_seconds=1.0)
    lock._recover_stale_lock()
    # Must NOT unlink rec_lock while its owner process is alive, even if older than stale_seconds
    assert rec_lock.exists()


def test_fallback_prune_skips_victim_updated_in_the_meantime():
    mock_redis = ControlledMockRedis()
    mock_redis.eval = None
    backend = RedisConversationBackend(mock_redis, max_conversations=1)
    user = DummyUser("user_victim")
    c1 = "conv_1"
    c2 = "conv_2"

    # Pre-populate index with c1 at t=100
    mock_redis.zadd("conv:_index", {c1: 100.0})
    mock_redis.set(c1, '{"data": "c1_data"}')

    # Mock zscore on c1 to return 200.0 (simulating another worker updated c1)
    real_zscore = mock_redis.zscore
    def updated_zscore(key, member):
        if member == c1:
            return 200.0  # Freshly updated!
        return real_zscore(key, member)
    mock_redis.zscore = updated_zscore

    # Now prune when c2 is recorded
    backend._prune_excess_conversations(c2, now=150.0)

    # c1 must NOT have been deleted because its score was updated!
    assert mock_redis.get(c1) is not None


def test_fallback_prune_watch_aborts_deletion_on_concurrent_update():
    mock_redis = ControlledMockRedis()
    mock_redis.eval = None
    backend = RedisConversationBackend(mock_redis, max_conversations=1)
    c1 = "conv_watch_1"
    c2 = "conv_watch_2"

    mock_redis.zadd("conv:_index", {c1: 100.0})
    mock_redis.set(c1, '{"data": "c1_data"}')

    # Simulate another worker updating c1 right after watch
    original_watch = MockRedisPipeline.watch
    def race_watch(self_pipe, *keys):
        res = original_watch(self_pipe, *keys)
        # Modify c1 in Redis to trigger WatchError on execute!
        mock_redis.set(c1, '{"data": "concurrent_fresh_update"}')
        return res

    mock_redis.pipeline = lambda: MockRedisPipeline(mock_redis)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MockRedisPipeline, "watch", race_watch)
        backend._prune_excess_conversations(c2, now=150.0)

    # c1 was updated concurrently; WatchError aborted the transaction so c1 is preserved!
    assert mock_redis.get(c1) == '{"data": "concurrent_fresh_update"}'


def test_recovery_mutex_replacement_race_does_not_unlink_new_owner(tmp_path, monkeypatch):
    lock_file = tmp_path / "race_rec.lock"
    lock_file.write_text("99999999:1000.0", encoding="utf-8")
    old_time = time.time() - 100.0
    os.utime(lock_file, (old_time, old_time))

    rec_lock = lock_file.with_suffix(".recover")
    rec_lock.write_text("99999999:1000.0", encoding="utf-8")
    os.utime(rec_lock, (old_time, old_time))

    from promption.state import _ProcessFileLock
    lock = _ProcessFileLock(lock_file, timeout=0.1, stale_seconds=1.0)

    # Simulate another process acquiring rec_lock between check and unlink
    original_read_text = Path.read_text
    reads = 0
    def mock_read_text(self_path, *args, **kwargs):
        nonlocal reads
        if self_path == rec_lock:
            reads += 1
            if reads == 1:
                return "99999999:1000.0"
            else:
                return f"{os.getpid()}:{time.time()}"
        return original_read_text(self_path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    lock._recover_stale_lock()
    # Must NOT unlink rec_lock because it was replaced by a new owner
    assert rec_lock.exists()


def test_lock_conserved_when_psutil_missing_and_owner_cannot_be_verified(tmp_path, monkeypatch):
    lock_file = tmp_path / "no_psutil.lock"
    # Live process PID with old timestamp
    lock_file.write_text(f"{os.getpid()}:{time.time()}", encoding="utf-8")
    old_time = time.time() - 100.0
    os.utime(lock_file, (old_time, old_time))

    import sys
    monkeypatch.setitem(sys.modules, "psutil", None)

    from promption.state import _ProcessFileLock, StatePersistenceError
    lock = _ProcessFileLock(lock_file, timeout=0.1, stale_seconds=1.0)
    with pytest.raises(StatePersistenceError):
        with lock:
            pass
    # Without psutil, lock of live process must be conserved, not deleted as stale!
    assert lock_file.exists()


def test_fallback_prune_retries_after_watch_error():
    mock_redis = ControlledMockRedis()
    mock_redis.eval = None
    backend = RedisConversationBackend(mock_redis, max_conversations=1)
    c1 = "conv_retry_1"
    c2 = "conv_retry_2"

    mock_redis.zadd("conv:_index", {c1: 100.0})
    mock_redis.set(c1, '{"data": "c1_initial"}')

    original_watch = MockRedisPipeline.watch
    watch_count = 0
    def race_watch_once(self_pipe, *keys):
        nonlocal watch_count
        watch_count += 1
        res = original_watch(self_pipe, *keys)
        if watch_count == 1:
            # Trigger WatchError on the first attempt only
            mock_redis.set(c1, '{"data": "c1_collision"}')
        return res

    mock_redis.pipeline = lambda: MockRedisPipeline(mock_redis)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MockRedisPipeline, "watch", race_watch_once)
        backend._prune_excess_conversations(c2, now=150.0)

    # Prune should have retried after WatchError and cleaned up excess down to max_conversations (1)
    assert mock_redis.zcard("conv:_index") == 1
    assert mock_redis.get(c1) is None





# ----------------------------------------------------------------------
# 18. Training Split Compatibility for CSV without source
# ----------------------------------------------------------------------
def test_create_splits_custom_csv_without_source():
    import pandas as pd
    from promption.training.split import create_splits

    df = pd.DataFrame({
        "prompt": ["hello", "world", "test attack", "another"],
        "label": [0, 0, 1, 1],
    })
    train_idx, val_idx, test_idx, ext_idx = create_splits(df)
    assert len(train_idx) + len(val_idx) + len(test_idx) + len(ext_idx) == len(df)


# ----------------------------------------------------------------------
# 19. BodySizeLimitMiddleware Streaming Receive Delegation
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_body_size_middleware_streaming_delegates_to_receive():
    from promption.limiter import BodySizeLimitMiddleware

    calls = 0
    async def mock_receive():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b"initial body", "more_body": False}
        elif calls == 2:
            return {"type": "http.disconnect"}
        return {"type": "http.disconnect"}

    received_messages = []
    async def dummy_app(scope, receive, send):
        msg1 = await receive()
        received_messages.append(msg1)
        msg2 = await receive()
        received_messages.append(msg2)

    middleware = BodySizeLimitMiddleware(dummy_app, max_bytes=1000)
    scope = {"type": "http", "headers": []}
    await middleware(scope, mock_receive, lambda msg: None)

    assert received_messages[0]["body"] == b"initial body"
    assert received_messages[1]["type"] == "http.disconnect"


# ----------------------------------------------------------------------
# 20. Chat Service require_trusted_client security enforcement
# ----------------------------------------------------------------------
def test_chat_service_require_trusted_client_auth(monkeypatch):
    from fastapi import HTTPException
    import sys
    from pathlib import Path

    chat_service_path = str(Path(__file__).parent.parent / "chat-service")
    if chat_service_path not in sys.path:
        sys.path.insert(0, chat_service_path)

    from app.config import settings
    from app.routes import require_trusted_client

    # 1. debug=False, no token configured -> MUST reject requests (401)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "chat_service_token", "")
    with pytest.raises(HTTPException) as exc_info:
        require_trusted_client(x_chat_service_token=None)
    assert exc_info.value.status_code == 401
    assert "token is required" in exc_info.value.detail

    # 2. debug=True, no token configured -> allowed
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "chat_service_token", "")
    require_trusted_client(x_chat_service_token=None)  # No exception

    # 3. token configured -> requires valid token regardless of debug
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "chat_service_token", "secret-key-123")
    with pytest.raises(HTTPException) as exc_info:
        require_trusted_client(x_chat_service_token="wrong-token")
    assert exc_info.value.status_code == 401

    require_trusted_client(x_chat_service_token="secret-key-123")  # Valid token succeeds


# ----------------------------------------------------------------------
# 21. Redis URL Credential Masking in Logs
# ----------------------------------------------------------------------
def test_redis_url_credential_masking():
    from promption.limiter import _mask_redis_url

    url_with_auth = "redis://user:supersecretpass@redis.prod.internal:6379/2"
    masked = _mask_redis_url(url_with_auth)
    assert "supersecretpass" not in masked
    assert "***" in masked
    assert "redis.prod.internal" in masked

    url_no_auth = "redis://localhost:6379/0"
    assert _mask_redis_url(url_no_auth) == url_no_auth

    url_query_auth = "redis://localhost:6379/0?password=secretquerytoken&ssl=true"
    masked_query = _mask_redis_url(url_query_auth)
    assert "secretquerytoken" not in masked_query
    assert "password=***" in masked_query
    assert "ssl=true" in masked_query

    url_ssl_auth = "rediss://redis.prod:6379/0?ssl_password=super_tls_pass&ssl_cert_reqs=required"
    masked_ssl = _mask_redis_url(url_ssl_auth)
    assert "super_tls_pass" not in masked_ssl
    assert "ssl_password=***" in masked_ssl
    assert "ssl_cert_reqs=required" in masked_ssl


# ----------------------------------------------------------------------
# 22. Guard Exceptions Do Not Print Unsanitized Traceback to Stderr
# ----------------------------------------------------------------------
def test_guard_exceptions_do_not_print_traceback_to_stderr(capsys):
    from promption.guard import Promption, Identity

    class BrokenFilter:
        def analyze(self, text, **kwargs):
            raise RuntimeError(f"Sensitive input: {text}")

    pipeline = Promption(input_filter=BrokenFilter())
    decision = pipeline.check_input("SUPER_SECRET_TOKEN_XYZ", Identity("guest"))
    assert not decision.allowed
    assert decision.reason == "guard_unavailable"
    assert decision.status == 503

    captured = capsys.readouterr()
    assert "SUPER_SECRET_TOKEN_XYZ" not in captured.err
    assert "Traceback" not in captured.err

# ----------------------------------------------------------------------
# 23. Real Multi-Process Mutual Exclusion and Crash Recovery with OS Lock
# ----------------------------------------------------------------------
def test_multiprocess_filelock_mutual_exclusion_and_recovery(tmp_path):
    import subprocess
    import sys
    import time
    from promption.state import _ProcessFileLock

    lp = tmp_path / "test_multiprocess.lock"
    child_script = """
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from promption.state import _ProcessFileLock
lock = _ProcessFileLock(Path(sys.argv[1]), timeout=1.0)
with lock:
    print("CHILD_LOCKED", flush=True)
    time.sleep(0.8)
    print("CHILD_DONE", flush=True)
"""
    p = subprocess.Popen([sys.executable, "-c", child_script, str(lp)], stdout=subprocess.PIPE, text=True)
    try:
        line = p.stdout.readline().strip()
        assert line == "CHILD_LOCKED", f"Expected CHILD_LOCKED, got {line}"

        # Try to acquire in parent - must wait for child to finish!
        parent_lock = _ProcessFileLock(lp, timeout=3.0)
        t0 = time.time()
        with parent_lock:
            t1 = time.time()
            assert t1 - t0 >= 0.5, f"Parent acquired too quickly: {t1 - t0}s"
    finally:
        p.wait()

    # Test abrupt termination (simulated crash)
    child_crash = """
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from promption.state import _ProcessFileLock
lock = _ProcessFileLock(Path(sys.argv[1]), timeout=1.0)
with lock:
    print("CRASH_LOCKED", flush=True)
    time.sleep(10.0)
"""
    p2 = subprocess.Popen([sys.executable, "-c", child_crash, str(lp)], stdout=subprocess.PIPE, text=True)
    try:
        line2 = p2.stdout.readline().strip()
        assert line2 == "CRASH_LOCKED"
        p2.kill()
    finally:
        p2.wait()

    # The OS automatically releases the OS lock so parent can acquire without hanging!
    t2 = time.time()
    recovery_lock = _ProcessFileLock(lp, timeout=1.0, stale_seconds=0.1)
    time.sleep(0.15)
    with recovery_lock:
        assert time.time() - t2 < 1.0

