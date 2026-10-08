"""Bounded conversation history owned by the chat service with shared backend support."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict
from pathlib import Path
from typing import Any, Protocol

from .conversation_guard import ConversationLimitError, validate_messages

logger = logging.getLogger(__name__)


class ConversationUser(Protocol):
    id: str
    roles: list
    authenticated: bool


TTL_SECONDS = 8 * 60 * 60
MAX_CONVERSATIONS = 500
MAX_TURNS = 12
MAX_CONTEXT_CHARS = 12_000


def _serialize_key(key: tuple) -> str:
    tenant_id, user_id, roles, authenticated, identifier = key
    return "conv:" + json.dumps(
        [tenant_id or "default", str(user_id), list(roles), bool(authenticated), str(identifier)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


class ConversationBackend(ABC):
    """Abstract storage backend for conversation history and security evidence."""

    @abstractmethod
    def get(self, key: tuple) -> dict | None:
        """Retrieve conversation data dict or None."""

    @abstractmethod
    def atomic_append_security(
        self, key: tuple, messages: list[dict], max_context_chars: int, ttl_seconds: int
    ) -> dict:
        """Atomically append security messages, validating limits."""

    @abstractmethod
    def atomic_record_turn(
        self,
        key: tuple,
        prompt: str,
        response: str,
        tier: str,
        actions: list[dict],
        max_turns: int,
        ttl_seconds: int,
    ) -> dict:
        """Atomically record a conversation turn."""

    @abstractmethod
    def mark_security_overflow(self, key: tuple) -> None:
        """Mark conversation as having overflowed security limits."""


class MemoryConversationBackend(ConversationBackend):
    """In-memory backend for explicit single-process mode."""

    def __init__(self, max_conversations: int = MAX_CONVERSATIONS):
        self.max_conversations = max_conversations
        self._items: OrderedDict[tuple, dict] = OrderedDict()
        self._lock = threading.Lock()

    def _prune(self, now: float, ttl_seconds: int) -> None:
        for k in list(self._items):
            if now - self._items[k].get("updated", 0) > ttl_seconds:
                del self._items[k]
        while len(self._items) > self.max_conversations:
            self._items.popitem(last=False)

    def get(self, key: tuple, ttl_seconds: int = TTL_SECONDS) -> dict | None:
        now = time.monotonic()
        with self._lock:
            self._prune(now, ttl_seconds)
            item = self._items.get(key)
            if item:
                self._items.move_to_end(key)
                return dict(item)
            return None

    def atomic_append_security(
        self, key: tuple, messages: list[dict], max_context_chars: int, ttl_seconds: int
    ) -> dict:
        now = time.monotonic()
        with self._lock:
            self._prune(now, ttl_seconds)
            item = self._items.setdefault(key, {"pairs": [], "security": [], "updated": now})
            evidence = item.get("security", []) + messages
            try:
                validate_messages(evidence)
            except ConversationLimitError:
                item["security_overflow"] = True
                raise
            item["security"] = [dict(m) for m in evidence]
            item["updated"] = now
            self._items.move_to_end(key)
            self._prune(now, ttl_seconds)
            return dict(item)

    def atomic_record_turn(
        self,
        key: tuple,
        prompt: str,
        response: str,
        tier: str,
        actions: list[dict],
        max_turns: int,
        ttl_seconds: int,
    ) -> dict:
        now = time.monotonic()
        with self._lock:
            self._prune(now, ttl_seconds)
            item = self._items.setdefault(key, {"pairs": [], "security": [], "updated": now})
            item["pairs"].append({
                "user": prompt[:5000],
                "assistant": response[:8000],
                "tier": tier,
                "actions": actions,
            })
            item["pairs"] = item["pairs"][-max_turns:]
            item["updated"] = now
            self._items.move_to_end(key)
            self._prune(now, ttl_seconds)
            return dict(item)

    def mark_security_overflow(self, key: tuple) -> None:
        with self._lock:
            item = self._items.setdefault(key, {"pairs": [], "security": [], "updated": time.monotonic()})
            item["security_overflow"] = True


class SQLiteConversationBackend(ConversationBackend):
    """Shared SQLite backend with WAL mode and atomic transactions for multi-process deployments."""

    def __init__(self, db_path: Path | str, max_conversations: int = MAX_CONVERSATIONS):
        self.db_path = Path(db_path)
        self.max_conversations = max_conversations
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    key TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    user_id TEXT,
                    data_json TEXT NOT NULL,
                    updated REAL NOT NULL,
                    version INTEGER DEFAULT 1
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated)")

    def _prune(self, conn: sqlite3.Connection, now: float, ttl_seconds: int) -> None:
        cutoff = now - ttl_seconds
        conn.execute("DELETE FROM conversations WHERE updated < ?", (cutoff,))
        # Enforce max_conversations
        cur = conn.execute("SELECT count(*) FROM conversations")
        count = cur.fetchone()[0]
        if count > self.max_conversations:
            excess = count - self.max_conversations
            conn.execute(
                "DELETE FROM conversations WHERE key IN (SELECT key FROM conversations ORDER BY updated ASC LIMIT ?)",
                (excess,),
            )

    def get(self, key: tuple, ttl_seconds: int = TTL_SECONDS) -> dict | None:
        str_key = _serialize_key(key)
        now = time.time()
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT data_json, updated FROM conversations WHERE key = ?", (str_key,))
            row = cur.fetchone()
            if not row:
                return None
            updated = row[1]
            if now - updated > ttl_seconds:
                conn.execute("DELETE FROM conversations WHERE key = ?", (str_key,))
                conn.commit()
                return None
            data = json.loads(row[0])
            return data

    def atomic_append_security(
        self, key: tuple, messages: list[dict], max_context_chars: int, ttl_seconds: int
    ) -> dict:
        str_key = _serialize_key(key)
        now = time.time()
        with self._lock, self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._prune(conn, now, ttl_seconds)
            cur = conn.execute("SELECT data_json, version FROM conversations WHERE key = ?", (str_key,))
            row = cur.fetchone()
            if row:
                item = json.loads(row[0])
                version = row[1] + 1
            else:
                item = {"pairs": [], "security": [], "updated": now}
                version = 1

            evidence = item.get("security", []) + messages
            try:
                validate_messages(evidence)
            except ConversationLimitError:
                item["security_overflow"] = True
                conn.execute(
                    "INSERT INTO conversations (key, tenant_id, user_id, data_json, updated, version) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET data_json=excluded.data_json, updated=excluded.updated, version=excluded.version",
                    (str_key, key[0], key[1], json.dumps(item), now, version),
                )
                conn.commit()
                raise

            item["security"] = [dict(m) for m in evidence]
            item["updated"] = now
            conn.execute(
                "INSERT INTO conversations (key, tenant_id, user_id, data_json, updated, version) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET data_json=excluded.data_json, updated=excluded.updated, version=excluded.version",
                (str_key, key[0], key[1], json.dumps(item), now, version),
            )
            conn.commit()
            return item

    def atomic_record_turn(
        self,
        key: tuple,
        prompt: str,
        response: str,
        tier: str,
        actions: list[dict],
        max_turns: int,
        ttl_seconds: int,
    ) -> dict:
        str_key = _serialize_key(key)
        now = time.time()
        with self._lock, self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._prune(conn, now, ttl_seconds)
            cur = conn.execute("SELECT data_json, version FROM conversations WHERE key = ?", (str_key,))
            row = cur.fetchone()
            if row:
                item = json.loads(row[0])
                version = row[1] + 1
            else:
                item = {"pairs": [], "security": [], "updated": now}
                version = 1

            item.setdefault("pairs", []).append({
                "user": prompt[:5000],
                "assistant": response[:8000],
                "tier": tier,
                "actions": actions,
            })
            item["pairs"] = item["pairs"][-max_turns:]
            item["updated"] = now
            conn.execute(
                "INSERT INTO conversations (key, tenant_id, user_id, data_json, updated, version) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET data_json=excluded.data_json, updated=excluded.updated, version=excluded.version",
                (str_key, key[0], key[1], json.dumps(item), now, version),
            )
            conn.commit()
            return item

    def mark_security_overflow(self, key: tuple) -> None:
        str_key = _serialize_key(key)
        now = time.time()
        with self._lock, self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("SELECT data_json, version FROM conversations WHERE key = ?", (str_key,))
            row = cur.fetchone()
            if row:
                item = json.loads(row[0])
                version = row[1] + 1
            else:
                item = {"pairs": [], "security": [], "updated": now}
                version = 1
            item["security_overflow"] = True
            conn.execute(
                "INSERT INTO conversations (key, tenant_id, user_id, data_json, updated, version) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET data_json=excluded.data_json, updated=excluded.updated, version=excluded.version",
                (str_key, key[0], key[1], json.dumps(item), now, version),
            )
            conn.commit()


class RedisConversationBackend(ConversationBackend):
    """Distributed Redis backend with TTL and atomic transactions."""

    _PRUNE_SCRIPT = """
    local index_key = KEYS[1]
    local current_key = ARGV[1]
    local now_ts = tonumber(ARGV[2])
    local max_conv = tonumber(ARGV[3])

    if now_ts > 0 then
        redis.call('ZADD', index_key, now_ts, current_key)
    end
    local total = redis.call('ZCARD', index_key)
    if total > max_conv then
        local excess = total - max_conv
        local oldest = redis.call('ZRANGE', index_key, 0, excess - 1)
        for _, k in ipairs(oldest) do
            if k ~= current_key then
                redis.call('DEL', k)
                redis.call('ZREM', index_key, k)
            end
        end
    end
    return total
    """

    def __init__(self, redis_client: Any, max_conversations: int = MAX_CONVERSATIONS):
        self.redis = redis_client
        self.max_conversations = max_conversations

    def _prune_excess_conversations(self, current_key: str, now: float = 0.0) -> None:
        index_key = "conv:_index"
        try:
            if callable(getattr(self.redis, "eval", None)):
                try:
                    self.redis.eval(
                        self._PRUNE_SCRIPT,
                        1,
                        index_key,
                        current_key,
                        str(now),
                        str(self.max_conversations),
                    )
                    return
                except Exception:
                    pass

            # Fallback for clients without eval support
            if now > 0 and hasattr(self.redis, "zadd"):
                self.redis.zadd(index_key, {current_key: now})

            pipe = getattr(self.redis, "pipeline", None)
            max_prune_attempts = 5
            for _ in range(max_prune_attempts):
                total = self.redis.zcard(index_key) if hasattr(self.redis, "zcard") else 0
                if total <= self.max_conversations or not hasattr(self.redis, "zrange"):
                    break
                excess = total - self.max_conversations
                candidates = self.redis.zrange(index_key, 0, min(total - 1, excess), withscores=True)
                if not candidates:
                    break

                any_pruned = False
                any_conflict = False
                if pipe:
                    for item in candidates:
                        curr_total = self.redis.zcard(index_key) if hasattr(self.redis, "zcard") else 0
                        if curr_total <= self.max_conversations:
                            break
                        k, score = item if isinstance(item, (tuple, list)) else (item, None)
                        k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                        if k_str == current_key:
                            continue
                        p = pipe()
                        try:
                            if hasattr(p, "watch"):
                                p.watch(k_str, index_key)
                            curr_score = self.redis.zscore(index_key, k_str) if hasattr(self.redis, "zscore") else score
                            if score is not None and curr_score is not None and float(curr_score) > float(score):
                                if hasattr(p, "reset"):
                                    p.reset()
                                any_conflict = True
                                continue
                            if hasattr(p, "multi"):
                                p.multi()
                            p.delete(k_str)
                            p.zrem(index_key, k_str)
                            p.execute()
                            any_pruned = True
                        except Exception:
                            any_conflict = True
                            continue
                        finally:
                            try:
                                if hasattr(p, "reset"):
                                    p.reset()
                            except Exception:
                                pass
                else:
                    for item in candidates:
                        curr_total = self.redis.zcard(index_key) if hasattr(self.redis, "zcard") else 0
                        if curr_total <= self.max_conversations:
                            break
                        k, score = item if isinstance(item, (tuple, list)) else (item, None)
                        k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                        if k_str == current_key:
                            continue
                        if score is not None and hasattr(self.redis, "zscore"):
                            curr_score = self.redis.zscore(index_key, k_str)
                            if curr_score is not None and float(curr_score) > float(score):
                                continue
                        self.redis.delete(k_str)
                        if hasattr(self.redis, "zrem"):
                            self.redis.zrem(index_key, k_str)
                        any_pruned = True

                if not any_pruned and not any_conflict:
                    break
        except Exception as exc:
            logger.debug("Failed to prune max conversations in Redis: %s", exc)

    def _enforce_max_conversations(self, current_key: str, now: float) -> None:
        self._prune_excess_conversations(current_key, now=now)

    def get(self, key: tuple, ttl_seconds: int = TTL_SECONDS) -> dict | None:
        str_key = _serialize_key(key)
        raw = self.redis.get(str_key)
        if raw is None:
            try:
                if hasattr(self.redis, "zrem"):
                    self.redis.zrem("conv:_index", str_key)
            except Exception:
                pass
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def atomic_append_security(
        self, key: tuple, messages: list[dict], max_context_chars: int, ttl_seconds: int
    ) -> dict:
        str_key = _serialize_key(key)
        max_retries = 10
        for _ in range(max_retries):
            pipe = self.redis.pipeline()
            try:
                pipe.watch(str_key)
                raw = pipe.get(str_key)
                if raw is not None:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    item = json.loads(raw)
                else:
                    item = {"pairs": [], "security": [], "updated": time.time()}

                evidence = item.get("security", []) + messages
                try:
                    validate_messages(evidence)
                except ConversationLimitError:
                    item["security_overflow"] = True
                    pipe.multi()
                    pipe.set(str_key, json.dumps(item), ex=ttl_seconds)
                    pipe.execute()
                    raise

                item["security"] = [dict(m) for m in evidence]
                item["updated"] = time.time()

                pipe.multi()
                pipe.set(str_key, json.dumps(item), ex=ttl_seconds)
                pipe.zadd("conv:_index", {str_key: item["updated"]})
                pipe.execute()
                self._prune_excess_conversations(str_key)
                return item
            except ConversationLimitError:
                raise
            except Exception:
                continue
            finally:
                try:
                    pipe.reset()
                except Exception:
                    pass

        raise RuntimeError("Failed to append security evidence in Redis after maximum retries")

    def atomic_record_turn(
        self,
        key: tuple,
        prompt: str,
        response: str,
        tier: str,
        actions: list[dict],
        max_turns: int,
        ttl_seconds: int,
    ) -> dict:
        str_key = _serialize_key(key)
        max_retries = 10
        for _ in range(max_retries):
            pipe = self.redis.pipeline()
            try:
                pipe.watch(str_key)
                raw = pipe.get(str_key)
                if raw is not None:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    item = json.loads(raw)
                else:
                    item = {"pairs": [], "security": [], "updated": time.time()}

                item.setdefault("pairs", []).append({
                    "user": prompt[:5000],
                    "assistant": response[:8000],
                    "tier": tier,
                    "actions": actions,
                })
                item["pairs"] = item["pairs"][-max_turns:]
                item["updated"] = time.time()

                pipe.multi()
                pipe.set(str_key, json.dumps(item), ex=ttl_seconds)
                pipe.zadd("conv:_index", {str_key: item["updated"]})
                pipe.execute()
                self._prune_excess_conversations(str_key)
                return item
            except Exception:
                continue
            finally:
                try:
                    pipe.reset()
                except Exception:
                    pass

        raise RuntimeError("Failed to record turn in Redis after maximum retries")

    def mark_security_overflow(self, key: tuple) -> None:
        str_key = _serialize_key(key)
        max_retries = 10
        for _ in range(max_retries):
            pipe = self.redis.pipeline()
            try:
                pipe.watch(str_key)
                raw = self.redis.get(str_key) if hasattr(self.redis, "get") else pipe.get(str_key)
                ttl = self.redis.ttl(str_key) if hasattr(self.redis, "ttl") else None
                if ttl is None or ttl <= 0:
                    ttl = TTL_SECONDS

                if raw is not None:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    item = json.loads(raw)
                else:
                    item = {"pairs": [], "security": [], "updated": time.time()}
                item["security_overflow"] = True

                pipe.multi()
                pipe.set(str_key, json.dumps(item), ex=ttl)
                pipe.execute()
                return
            except Exception:
                continue
            finally:
                try:
                    pipe.reset()
                except Exception:
                    pass
        raise RuntimeError("Failed to mark security overflow in Redis after maximum retries")


class ConversationStore:
    def __init__(
        self,
        *,
        tenant_id: str | None = None,
        ttl_seconds: int = TTL_SECONDS,
        max_conversations: int = MAX_CONVERSATIONS,
        max_turns: int = MAX_TURNS,
        max_context_chars: int = MAX_CONTEXT_CHARS,
        backend: ConversationBackend | None = None,
    ):
        if min(ttl_seconds, max_conversations, max_turns, max_context_chars) < 1:
            raise ValueError("Conversation limits must be positive")
        self.tenant_id = tenant_id
        self.ttl_seconds = ttl_seconds
        self.max_conversations = max_conversations
        self.max_turns = max_turns
        self.max_context_chars = max_context_chars
        self.backend = backend or MemoryConversationBackend(max_conversations=max_conversations)
        if hasattr(self.backend, "max_conversations"):
            self.backend.max_conversations = max_conversations

    def _key(self, conversation_id: str | None, user: ConversationUser):
        try:
            identifier = str(uuid.UUID(conversation_id or ""))
        except (ValueError, AttributeError, TypeError):
            return None
        roles = tuple(sorted(role.value if hasattr(role, "value") else str(role)
                             for role in user.roles))
        return self.tenant_id, user.id, roles, bool(user.authenticated), identifier

    def snapshot(self, conversation_id: str | None, user: ConversationUser) -> tuple[list[dict], bool]:
        key = self._key(conversation_id, user)
        if key is None:
            return [], False
        item = self.backend.get(key, ttl_seconds=self.ttl_seconds)
        if not item:
            return [], False
        pairs = list(item.get("pairs", []))
        selected = []
        total = 0
        for pair in reversed(pairs):
            size = len(pair["user"]) + len(pair["assistant"])
            if total + size > self.max_context_chars:
                break
            selected.append(pair)
            total += size
        selected.reverse()
        messages = []
        for pair in selected:
            messages.extend((
                {"role": "user", "content": pair["user"]},
                {"role": "assistant", "content": pair["assistant"]},
            ))
        protected = any(pair["tier"] in {"interno", "confidencial", "restringido"}
                        for pair in selected)
        return messages, protected

    def security_snapshot(self, conversation_id: str | None, user: ConversationUser) -> list[dict]:
        key = self._key(conversation_id, user)
        if key is None:
            return []
        item = self.backend.get(key, ttl_seconds=self.ttl_seconds)
        if not item:
            return []
        if item.get("security_overflow"):
            raise ConversationLimitError("Security evidence exceeds limits; start a new conversation")
        # Fail-closed if security evidence was lost or missing while conversation history exists
        if item.get("security_lost") or (item.get("pairs") and not item.get("security")):
            raise ConversationLimitError("Security evidence is unavailable; start a new conversation")
        return [dict(message) for message in item.get("security", [])]

    def append_security(self, conversation_id: str | None, user: ConversationUser, messages: list[dict]) -> None:
        key = self._key(conversation_id, user)
        if key is None:
            return
        self.backend.atomic_append_security(key, messages, self.max_context_chars, self.ttl_seconds)

    def display(self, conversation_id: str | None, user: ConversationUser) -> list[dict]:
        key = self._key(conversation_id, user)
        if key is None:
            return []
        item = self.backend.get(key, ttl_seconds=self.ttl_seconds)
        if not item:
            return []
        pairs = list(item.get("pairs", []))
        visible = []
        for pair in pairs:
            visible.append({"from": "user", "text": pair["user"]})
            visible.append({"from": "bot", "text": pair["assistant"],
                            "actions": pair.get("actions", [])})
        return visible

    def record(
        self,
        conversation_id: str | None,
        user: ConversationUser,
        prompt: str,
        response: str,
        tier: str,
        actions: list[dict],
        *,
        security_recorded: bool = False,
    ):
        key = self._key(conversation_id, user)
        if key is None:
            return
        if not security_recorded:
            self.append_security(conversation_id, user, [{"role": "user", "content": prompt}])
        self.backend.atomic_record_turn(
            key, prompt, response, tier, actions, self.max_turns, self.ttl_seconds
        )
