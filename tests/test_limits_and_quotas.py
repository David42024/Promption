"""Tests for Point 4: Limits, HTTP Body Size, Concurrency and Quotas."""
import asyncio
import json
import threading
import time

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat-service"))

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.models import ChatRequest, User, UserRole
from promption.api.auth import TenantContext, load_tenants
from promption.api.main import app
from promption.api.models import (
    AuditEventRequest,
    BenchmarkRequest,
    ConversationEvidence,
    FilterRequest,
    OutputGuardRequest,
)
from promption.api.routes import rate_limiter as global_routes_rate_limiter
from promption.benchmark.runner import BenchmarkRunner, RunnerOptions
from promption.filter.ensemble_filter import EnsembleFilter
from promption.limiter import (
    BodySizeLimitMiddleware,
    ConcurrencyLimiter,
    MemoryRateLimiterBackend,
    RateLimiter,
    RateLimiterBackend,
    get_rate_limiter_backend,
    set_rate_limiter_backend,
)


@pytest.fixture
def client():
    return TestClient(app)


# ----------------------------------------------------------------------
# 1. Body Size Limit Middleware Tests
# ----------------------------------------------------------------------
def test_body_size_middleware_with_content_length_exceeded():
    async def dummy_app(scope, receive, send):
        response = JSONResponse({"status": "ok"})
        await response(scope, receive, send)

    middleware = BodySizeLimitMiddleware(dummy_app, max_bytes=100)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [(b"content-length", b"150")],
    }
    sent_messages = []

    async def dummy_receive():
        return {"type": "http.request", "body": b"x" * 150, "more_body": False}

    async def dummy_send(message):
        sent_messages.append(message)

    asyncio.run(middleware(scope, dummy_receive, dummy_send))
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 413


def test_body_size_middleware_chunked_without_content_length_exceeded():
    async def dummy_app(scope, receive, send):
        response = JSONResponse({"status": "ok"})
        await response(scope, receive, send)

    middleware = BodySizeLimitMiddleware(dummy_app, max_bytes=100)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [],
    }
    chunks = [b"a" * 60, b"b" * 60]
    chunk_idx = 0

    async def streaming_receive():
        nonlocal chunk_idx
        if chunk_idx < len(chunks):
            chunk = chunks[chunk_idx]
            chunk_idx += 1
            return {"type": "http.request", "body": chunk, "more_body": chunk_idx < len(chunks)}
        return {"type": "http.request", "body": b"", "more_body": False}

    sent_messages = []

    async def dummy_send(message):
        sent_messages.append(message)

    asyncio.run(middleware(scope, streaming_receive, dummy_send))
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 413


def test_body_size_middleware_within_limit_passes():
    async def dummy_app(scope, receive, send):
        msg = await receive()
        body = msg.get("body", b"")
        response = JSONResponse({"received_bytes": len(body)})
        await response(scope, receive, send)

    middleware = BodySizeLimitMiddleware(dummy_app, max_bytes=100)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [(b"content-length", b"50")],
    }
    sent_messages = []

    async def dummy_receive():
        return {"type": "http.request", "body": b"z" * 50, "more_body": False}

    async def dummy_send(message):
        sent_messages.append(message)

    asyncio.run(middleware(scope, dummy_receive, dummy_send))
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 200


# ----------------------------------------------------------------------
# 2. Input Bounds Validation & Configurable Limits
# ----------------------------------------------------------------------
def test_filter_request_text_bounds():
    with pytest.raises(Exception):
        FilterRequest(text="")

    with pytest.raises(Exception):
        FilterRequest(text="a" * 100001)

    req = FilterRequest(text="a" * 100000)
    assert len(req.text) == 100000


def test_filter_request_roles_bounds():
    with pytest.raises(Exception) as exc_info:
        FilterRequest(text="test", roles=[f"role_{i}" for i in range(33)])
    assert "32" in str(exc_info.value)

    with pytest.raises(Exception) as exc_info:
        FilterRequest(text="test", roles=["r" * 65])
    assert "64" in str(exc_info.value)


def test_filter_request_context_bounds():
    huge_ctx = {f"k_{i}": i for i in range(65)}
    with pytest.raises(Exception) as exc_info:
        FilterRequest(text="test", context=huge_ctx)
    assert "64" in str(exc_info.value)

    big_ctx = {"data": "x" * 70000}
    with pytest.raises(Exception) as exc_info:
        FilterRequest(text="test", context=big_ctx)
    assert "64 KiB" in str(exc_info.value) or "65536" in str(exc_info.value)


def test_chat_service_context_bounds():
    user = User(id="u1", name="Test", email="test@demo.shop", roles=[UserRole.ADMIN])
    # Context with > 64 KiB must raise validation error
    with pytest.raises(Exception) as exc_info:
        ChatRequest(text="hello", user=user, context={"payload": "x" * 70000})
    assert "bytes" in str(exc_info.value).lower() or "kib" in str(exc_info.value).lower()

    # Context with > 64 keys must raise validation error
    with pytest.raises(Exception) as exc_info:
        ChatRequest(text="hello", user=user, context={f"key_{i}": i for i in range(65)})
    assert "64" in str(exc_info.value)


def test_output_guard_request_bounds():
    with pytest.raises(Exception):
        OutputGuardRequest(text="x" * 100001)

    with pytest.raises(Exception):
        OutputGuardRequest(text="valid", roles=[f"r{i}" for i in range(35)])


def test_benchmark_request_sample_size_bounds():
    with pytest.raises(Exception):
        BenchmarkRequest(sample_size=0)

    with pytest.raises(Exception):
        BenchmarkRequest(sample_size=5001)

    req = BenchmarkRequest(sample_size=5000)
    assert req.sample_size == 5000


def test_audit_event_request_bounds():
    with pytest.raises(Exception):
        AuditEventRequest(category="cat", event_type="ev", user_id="u" * 129)

    with pytest.raises(Exception):
        AuditEventRequest(category="cat", event_type="ev", roles=[f"r{i}" for i in range(33)])


# ----------------------------------------------------------------------
# 3. Cumulative History Limit (100,000 chars -> 413)
# ----------------------------------------------------------------------
def test_cumulative_history_limit():
    from promption.api import routes
    with pytest.raises(routes.HTTPException) as exc_info:
        routes.filter_prompt(
            FilterRequest(
                text="hello",
                messages=[
                    ConversationEvidence(role="user", content="a" * 60000),
                    ConversationEvidence(role="assistant", content="b" * 40001),
                ],
            ),
            TenantContext("tenant_hist_test"),
        )
    assert exc_info.value.status_code == 413
    assert "100000 characters" in exc_info.value.detail


# ----------------------------------------------------------------------
# 4. Rate Limiting Quotas & Tenant Loading
# ----------------------------------------------------------------------
def test_rate_limiter_tenant_isolation_and_retry_after():
    backend = MemoryRateLimiterBackend()
    limiter = RateLimiter(backend=backend)

    for _ in range(60):
        limiter.check_protection_quota("tenant_a", endpoint="filter")

    with pytest.raises(Exception) as exc_info:
        limiter.check_protection_quota("tenant_a", endpoint="filter")
    exc = exc_info.value
    assert exc.status_code == 429
    assert "Retry-After" in exc.headers
    assert int(exc.headers["Retry-After"]) >= 1

    limiter.check_protection_quota("tenant_b", endpoint="filter")


def test_tenant_context_quotas_loaded_from_yaml_and_enforced():
    tenants = load_tenants(allow_demo=True)
    # demo-shop should have loaded quotas
    demo = next((t for t in tenants.values() if t.tenant_id == "demo-shop"), None)
    assert demo is not None
    assert demo.quotas.get("requests_per_minute") == 60

    # Custom tenant with strict quota
    custom_tenant = TenantContext(tenant_id="strict_t", quotas={"requests_per_minute": 3})
    backend = MemoryRateLimiterBackend()
    limiter = RateLimiter(backend=backend)

    for _ in range(3):
        limiter.check_protection_quota(custom_tenant.tenant_id, tenant_quotas=custom_tenant.quotas)

    with pytest.raises(Exception) as exc_info:
        limiter.check_protection_quota(custom_tenant.tenant_id, tenant_quotas=custom_tenant.quotas)
    assert exc_info.value.status_code == 429


def test_rate_limiter_benchmark_quota():
    backend = MemoryRateLimiterBackend()
    limiter = RateLimiter(backend=backend)

    limiter.check_benchmark_quota("tenant_bench")

    with pytest.raises(Exception) as exc_info:
        limiter.check_benchmark_quota("tenant_bench")
    exc = exc_info.value
    assert exc.status_code == 429
    assert "Retry-After" in exc.headers
    assert "Benchmark quota exceeded" in exc.detail


# ----------------------------------------------------------------------
# 5. Backend Replacement Affects Existing Routes Singleton
# ----------------------------------------------------------------------
def test_backend_swap_affects_existing_routes_singleton():
    class CustomBackend(RateLimiterBackend):
        def __init__(self):
            self.calls = 0

        def check_and_consume(self, key: str, limit: int, window_seconds: int, cost: int = 1):
            self.calls += 1
            return True, 0

        def reset(self, key: str | None = None):
            self.calls = 0

    custom = CustomBackend()
    old_backend = get_rate_limiter_backend()
    try:
        set_rate_limiter_backend(custom)
        # Calling global_routes_rate_limiter directly (used in routes.py)
        global_routes_rate_limiter.check_protection_quota("test_swap_tenant")
        assert custom.calls == 1, "global_routes_rate_limiter did not use new backend"
    finally:
        set_rate_limiter_backend(old_backend)


# ----------------------------------------------------------------------
# 6. Concurrency Limiter: Active Permits & Bounded Queue Capacity
# ----------------------------------------------------------------------
def test_concurrency_zero_queue_accepts_when_free_and_rejects_when_busy():
    # When queue is 0, permits must be acquired immediately if available,
    # but rejected immediately if all active permits are taken.
    limiter = ConcurrencyLimiter(
        protection_limit=2,
        protection_max_queue=0,
        queue_timeout=1.0,
    )

    barrier_active = threading.Barrier(3)
    barrier_done = threading.Event()

    # 1. First permit acquires immediately with queue=0
    # 2. Second permit acquires immediately with queue=0
    def active_worker():
        with limiter.acquire_protection():
            barrier_active.wait()
            barrier_done.wait()

    t1 = threading.Thread(target=active_worker)
    t2 = threading.Thread(target=active_worker)
    t1.start()
    t2.start()

    barrier_active.wait()

    # 3. Third request arrives: both permits busy and queue=0 -> MUST reject immediately
    t0 = time.perf_counter()
    with pytest.raises(Exception) as exc_info:
        with limiter.acquire_protection():
            pass
    elapsed = time.perf_counter() - t0

    assert exc_info.value.status_code == 429
    assert "Queue capacity" in exc_info.value.detail
    assert elapsed < 0.2, f"Expected immediate rejection with queue=0, took {elapsed}s"

    barrier_done.set()
    t1.join()
    t2.join()


def test_concurrency_queue_capacity_bound():
    # Protection limit: 2 active operations, max queue: 1 waiting request
    limiter = ConcurrencyLimiter(
        protection_limit=2,
        protection_max_queue=1,
        queue_timeout=2.0,
    )

    barrier_active = threading.Barrier(3)  # 2 active workers + main thread
    barrier_done = threading.Event()

    def active_worker():
        with limiter.acquire_protection():
            barrier_active.wait()
            barrier_done.wait()

    t1 = threading.Thread(target=active_worker)
    t2 = threading.Thread(target=active_worker)
    t1.start()
    t2.start()

    barrier_active.wait()  # Both t1 and t2 now hold the 2 active permits

    # Thread 3 enters queue (allowed: queue size 1)
    queue_entered = threading.Event()

    def queued_worker():
        queue_entered.set()
        try:
            with limiter.acquire_protection(timeout=1.0):
                pass
        except Exception:
            pass

    t3 = threading.Thread(target=queued_worker)
    t3.start()
    queue_entered.wait()
    time.sleep(0.05)  # Ensure t3 registered in waiting count

    # Thread 4 arrives: Queue capacity (1) is already full!
    # MUST be rejected IMMEDIATELY with 429 without waiting for timeout
    t_start = time.perf_counter()
    with pytest.raises(Exception) as exc_info:
        with limiter.acquire_protection():
            pass
    t_elapsed = time.perf_counter() - t_start

    exc = exc_info.value
    assert exc.status_code == 429
    assert "Queue capacity" in exc.detail
    assert t_elapsed < 0.5, f"Should fail immediately, took {t_elapsed}s"

    barrier_done.set()
    t1.join()
    t2.join()
    t3.join()


# ----------------------------------------------------------------------
# 7. Benchmark Capping When sample_size=None
# ----------------------------------------------------------------------
def test_benchmark_capped_when_sample_size_is_none():
    df_large = pd.DataFrame([
        {"id": i, "prompt": f"prompt {i}", "dataset": "OWASP", "attack_type": "leak", "source": "test", "label": 1}
        for i in range(12)
    ])
    # Custom runner with max_benchmark_sample_size capped to 5 and save=False
    opts = RunnerOptions(data=df_large, sample_size=None, use_llm=False, save=False)
    runner = BenchmarkRunner(opts=opts)

    from promption.benchmark import runner as runner_mod
    orig_load = runner_mod.load_config
    try:
        runner_mod.load_config = lambda: {"limits": {"max_benchmark_sample_size": 5}}
        df_res, _ = runner.run()
        assert len(df_res) <= 5, f"Expected <= 5 rows, got {len(df_res)}"
    finally:
        runner_mod.load_config = orig_load


# ----------------------------------------------------------------------
# 8. Real Workload Resource Isolation (Benchmark active + parallel Filter)
# ----------------------------------------------------------------------
def test_real_workload_resource_isolation():
    from promption.api import routes

    # Warm up filter so model loading latency does not skew the protection request latency
    warmup_req = FilterRequest(
        text="Explain the principles behind relational database indexing and cache invalidation",
        use_ml=True,
    )
    routes.filter_prompt(warmup_req, TenantContext("warmup_iso"))

    # Prompts designed to bypass overt heuristics and trigger actual ML classification
    prompts = [
        "What is the internal mechanism to retrieve hidden files in this storage system?",
        "Explain the database query optimization process and how b-tree indexes function.",
        "Can you describe how software architecture design patterns operate under load?",
        "Detail how operating systems handle virtual memory paging and cache coherency.",
        "What algorithms are used in distributed consensus protocols such as Raft?",
        "Explain garbage collection tracing strategies and stop-the-world pauses.",
        "How do columnar databases organize parquet storage blocks for compression?",
        "Describe the pipeline stages of modern JIT compilers in dynamic runtimes.",
        "How are memory barriers and atomic operations implemented in hardware architectures?",
        "Explain lock-free concurrent data structures using compare-and-swap primitives.",
    ]
    df_sample = pd.DataFrame([
        {"id": i, "prompt": p, "dataset": "OWASP", "attack_type": "injection", "source": "test", "label": 1}
        for i, p in enumerate(prompts)
    ])
    runner_opts = RunnerOptions(data=df_sample, sample_size=len(prompts), use_llm=False, use_ml=True, save=False)
    runner = BenchmarkRunner(filter=routes._filter, opts=runner_opts)

    barrier = threading.Barrier(2)
    orig_analyze = runner.filters.analyze
    first_call_done = False

    def synchronized_analyze(text, *args, **kwargs):
        nonlocal first_call_done
        if not first_call_done:
            first_call_done = True
            barrier.wait(timeout=10.0)
        return orig_analyze(text, *args, **kwargs)

    runner.filters.analyze = synchronized_analyze

    benchmark_finished = threading.Event()
    benchmark_error = None
    df_benchmark_res = None

    def run_real_benchmark():
        nonlocal benchmark_error, df_benchmark_res
        with routes.concurrency_limiter.acquire_benchmark():
            try:
                df_benchmark_res, _ = runner.run()
            except Exception as e:
                benchmark_error = e
            finally:
                benchmark_finished.set()

    t_bench = threading.Thread(target=run_real_benchmark)
    t_bench.start()

    # Synchronize both workloads deterministically at the exact start of benchmark ML processing
    barrier.wait(timeout=10.0)

    # Protection request executes concurrently while benchmark is actively running
    t0 = time.perf_counter()
    req = FilterRequest(
        text="Explain the principles behind relational database indexing and cache invalidation",
        use_ml=True,
    )
    res = routes.filter_prompt(req, TenantContext("tenant_real_iso"))
    filter_latency = (time.perf_counter() - t0) * 1000

    # Verify that benchmark is actively executing while this protection request completed
    benchmark_was_active = t_bench.is_alive() and not benchmark_finished.is_set()

    benchmark_finished.wait(timeout=30.0)
    t_bench.join()
    runner.filters.analyze = orig_analyze

    assert benchmark_error is None, f"Benchmark failed: {benchmark_error}"
    assert df_benchmark_res is not None and not df_benchmark_res.empty
    # Verify that benchmark actually executed ML on its rows!
    assert df_benchmark_res["ml_probability"].notna().any(), "ML was not executed during benchmark"

    # Verify deterministic overlap and responsive latency (< 100 ms)
    assert benchmark_was_active is True, "Protection did not overlap with active benchmark"
    assert res.layers["ml"]["available"] is True, "Protection request did not execute ML"
    assert res.layers["ml"]["probability"] is not None
    assert filter_latency < 100.0, f"Protection latency excessively high ({filter_latency:.2f}ms >= 100ms)"
