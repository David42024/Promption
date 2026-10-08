"""Rate limiting, concurrency and body size bounds.

Implements:
- BodySizeLimitMiddleware: Enforces max_body_bytes (2 MiB) before deserialization,
  even without Content-Length. Returns HTTP 413.
- RateLimiter: Tenant-isolated rate limiting with configurable quotas per endpoint
  (e.g. 60 req/min for protection, 1 req/hour for benchmark). Returns HTTP 429 with Retry-After.
- ConcurrencyLimiter: Process-bounded concurrency (e.g. 4 protection, 1 benchmark)
  with bounded queue wait. Returns HTTP 429 on saturation.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException
from starlette.responses import JSONResponse

from promption.utils.config import load_config
from promption.utils.logger import logger


class BodySizeExceeded(Exception):
    """Raised when the request body exceeds maximum allowed bytes."""


class BodySizeLimitMiddleware:
    """ASGI middleware that enforces a maximum request body size before deserialization."""

    def __init__(self, app, max_bytes: int = 2 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        cl_header = headers.get(b"content-length")
        if cl_header:
            try:
                if int(cl_header.decode()) > self.max_bytes:
                    await self._send_413(send)
                    return
            except ValueError:
                pass

        body = bytearray()
        exceeded = False
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                body.extend(chunk)
                if len(body) > self.max_bytes:
                    exceeded = True
                    break
                more_body = message.get("more_body", False)
            else:
                break

        if exceeded:
            await self._send_413(send)
            return

        body_bytes = bytes(body)
        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, send)

    async def _send_413(self, send):
        response = JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds limit of {self.max_bytes} bytes"},
        )
        await response(scope={"type": "http"}, receive=None, send=send)


# ----------------------------------------------------------------------
# Rate Limiting Backend Interface & Memory Implementation
# ----------------------------------------------------------------------
class RateLimiterBackend(ABC):
    @abstractmethod
    def check_and_consume(self, key: str, limit: int, window_seconds: int, cost: int = 1) -> tuple[bool, int]:
        """Check if request is permitted and record it. Returns (allowed, retry_after_seconds)."""

    @abstractmethod
    def reset(self, key: str | None = None) -> None:
        """Reset history."""


class MemoryRateLimiterBackend(RateLimiterBackend):
    """In-memory sliding window rate limiter."""

    def __init__(self):
        self._lock = threading.Lock()
        self._history: dict[str, deque[float]] = defaultdict(deque)

    def check_and_consume(self, key: str, limit: int, window_seconds: int, cost: int = 1) -> tuple[bool, int]:
        with self._lock:
            now = time.time()
            cutoff = now - window_seconds
            timestamps = self._history[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) + cost > limit:
                oldest = timestamps[0] if timestamps else now
                retry_after = max(1, int(oldest + window_seconds - now))
                return False, retry_after

            for _ in range(cost):
                timestamps.append(now)
            return True, 0

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._history.clear()
            else:
                self._history.pop(key, None)


LUA_SLIDING_WINDOW_RATE_LIMIT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local token_prefix = ARGV[5]

local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local current = redis.call('ZCARD', key)

if current + cost > limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local oldest_ts = now
    if oldest and #oldest >= 2 then
        oldest_ts = tonumber(oldest[2])
    end
    local retry_after = math.max(1, math.floor(oldest_ts + window - now))
    return {0, retry_after}
end

for i = 1, cost do
    redis.call('ZADD', key, now, token_prefix .. '_' .. tostring(i))
end
redis.call('EXPIRE', key, math.floor(window) + 5)
return {1, 0}
"""


class RedisRateLimiterBackend(RateLimiterBackend):
    """Distributed Redis sliding window rate limiter using atomic Lua script."""

    def __init__(self, redis_client: Any, prefix: str = "ratelimit"):
        self.redis = redis_client
        self.prefix = prefix

    def _redis_key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def check_and_consume(self, key: str, limit: int, window_seconds: int, cost: int = 1) -> tuple[bool, int]:
        r_key = self._redis_key(key)
        now = time.time()
        token_prefix = f"{now}_{uuid.uuid4().hex[:8]}"

        try:
            res = self.redis.eval(
                LUA_SLIDING_WINDOW_RATE_LIMIT,
                1,
                r_key,
                now,
                window_seconds,
                limit,
                cost,
                token_prefix,
            )
            return bool(res[0]), int(res[1])
        except Exception:
            # Fallback to atomic WATCH/MULTI/EXEC transaction
            max_retries = 10
            for _ in range(max_retries):
                pipe = self.redis.pipeline()
                try:
                    pipe.watch(r_key)
                    cutoff = now - window_seconds
                    pipe.zremrangebyscore(r_key, "-inf", cutoff)
                    raw_items = self.redis.zrange(r_key, 0, -1, withscores=True) if hasattr(self.redis, "zrange") else []
                    valid_items = [(m, float(s)) for m, s in raw_items if float(s) > cutoff]
                    current_count = len(valid_items)

                    if current_count + cost > limit:
                        pipe.unwatch()
                        oldest_ts = valid_items[0][1] if valid_items else now
                        retry_after = max(1, int(oldest_ts + window_seconds - now))
                        return False, retry_after

                    pipe.multi()
                    pipe.zremrangebyscore(r_key, "-inf", cutoff)
                    member_dict = {f"{token_prefix}_{i}": now for i in range(cost)}
                    pipe.zadd(r_key, member_dict)
                    pipe.expire(r_key, int(window_seconds) + 5)
                    pipe.execute()
                    return True, 0
                except Exception:
                    continue
                finally:
                    try:
                        pipe.reset()
                    except Exception:
                        pass
            return False, 1

    def reset(self, key: str | None = None) -> None:
        if key is None:
            keys = self.redis.keys(f"{self.prefix}:*")
            if keys:
                self.redis.delete(*keys)
        else:
            self.redis.delete(self._redis_key(key))


def get_rate_limiter_backend() -> RateLimiterBackend:
    return _backend


def set_rate_limiter_backend(backend: RateLimiterBackend) -> None:
    global _backend
    _backend = backend


def _mask_redis_url(redis_url: str) -> str:
    try:
        import urllib.parse
        parsed = urllib.parse.urlsplit(redis_url)
        netloc = parsed.netloc
        if parsed.password:
            netloc = f"{parsed.username or ''}:***@{parsed.hostname or ''}"
            if parsed.port:
                netloc += f":{parsed.port}"

        query = parsed.query
        if query:
            params = urllib.parse.parse_qsl(query, keep_blank_values=True)
            masked_params = []
            for k, v in params:
                kl = k.lower()
                if any(s in kl for s in ("password", "pass", "pwd", "token", "secret", "auth", "credential")):
                    masked_params.append((k, "***"))
                else:
                    masked_params.append((k, v))
            query = urllib.parse.urlencode(masked_params, safe="*")

        return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))
    except Exception:
        return "redis://***"


def init_rate_limiter_from_config() -> RateLimiterBackend:
    """Initialize and configure global rate limiter backend from environment or config.yaml."""
    import os
    conf = load_config()
    backend_type = os.getenv("PROMPTION_RATE_LIMITER_BACKEND") or conf.get("limits", {}).get(
        "rate_limiter_backend", "memory"
    )
    if backend_type.lower() == "redis":
        redis_url = os.getenv("PROMPTION_REDIS_URL") or conf.get("limits", {}).get(
            "redis_url", "redis://localhost:6379/0"
        )
        try:
            import redis
            client = redis.from_url(redis_url)
            backend = RedisRateLimiterBackend(client)
            set_rate_limiter_backend(backend)
            masked_url = _mask_redis_url(redis_url)
            logger.info("Initialized shared RedisRateLimiterBackend from config/env at %s", masked_url)
            return backend
        except Exception as exc:
            logger.error("Failed to initialize RedisRateLimiterBackend: %s. Falling back to memory.", exc)
    backend = MemoryRateLimiterBackend()
    set_rate_limiter_backend(backend)
    return backend


# Singleton backend initialized from config or environment
_backend: RateLimiterBackend = MemoryRateLimiterBackend()
init_rate_limiter_from_config()


# ----------------------------------------------------------------------
# Rate Limiter Service
# ----------------------------------------------------------------------
class RateLimiter:
    """Manages rate limiting quotas for protection and benchmark endpoints."""

    def __init__(self, backend: RateLimiterBackend | None = None):
        self._custom_backend = backend

    @property
    def backend(self) -> RateLimiterBackend:
        if self._custom_backend is not None:
            return self._custom_backend
        return get_rate_limiter_backend()

    def check_protection_quota(self, tenant_id: str, endpoint: str = "filter",
                               cost: int = 1, tenant_quotas: dict | None = None) -> None:
        conf = load_config().get("limits", {}).get("rate_limit", {})
        rpm = int((tenant_quotas or {}).get("requests_per_minute") or conf.get("protection_rpm", 60))
        key = f"protection:{tenant_id}:{endpoint}"
        allowed, retry_after = self.backend.check_and_consume(key, limit=rpm, window_seconds=60, cost=cost)
        if not allowed:
            logger.warning("Tenant '%s' rate limit exceeded on '%s' (retry in %ds)", tenant_id, endpoint, retry_after)
            raise HTTPException(
                status_code=429,
                detail=f"Filter API rate limit exceeded ({rpm} req/min). Please retry later.",
                headers={"Retry-After": str(retry_after)},
            )

    def check_benchmark_quota(self, tenant_id: str, tenant_quotas: dict | None = None) -> None:
        conf = load_config().get("limits", {}).get("rate_limit", {})
        rph = int((tenant_quotas or {}).get("benchmarks_per_hour") or conf.get("benchmark_rph", 1))
        key = f"benchmark:{tenant_id}"
        allowed, retry_after = self.backend.check_and_consume(key, limit=rph, window_seconds=3600, cost=1)
        if not allowed:
            logger.warning("Tenant '%s' benchmark quota exceeded (retry in %ds)", tenant_id, retry_after)
            raise HTTPException(
                status_code=429,
                detail=f"Benchmark quota exceeded ({rph} run/hour). Please retry later.",
                headers={"Retry-After": str(retry_after)},
            )


# ----------------------------------------------------------------------
# Concurrency Limiter
# ----------------------------------------------------------------------
class _SemaphoreGuard:
    def __init__(
        self,
        limiter: ConcurrencyLimiter,
        semaphore: threading.BoundedSemaphore,
        timeout: float,
        error_detail: str,
        is_protection: bool = True,
    ):
        self.limiter = limiter
        self.semaphore = semaphore
        self.timeout = timeout
        self.error_detail = error_detail
        self.is_protection = is_protection
        self.acquired = False
        self.queued = False

    def __enter__(self):
        # 1. Try immediate acquisition without queueing if a permit is available
        if self.semaphore.acquire(blocking=False):
            self.acquired = True
            return self

        # 2. No immediate permit available -> check queue bounds
        with self.limiter._lock:
            current_waiting = (
                self.limiter._protection_waiting
                if self.is_protection
                else self.limiter._benchmark_waiting
            )
            max_waiting = (
                self.limiter.protection_max_queue
                if self.is_protection
                else self.limiter.benchmark_max_queue
            )
            if current_waiting >= max_waiting:
                logger.warning(
                    "Concurrency queue full for %s: %d waiting (limit %d)",
                    "protection" if self.is_protection else "benchmark",
                    current_waiting,
                    max_waiting,
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"{self.error_detail} (Queue capacity of {max_waiting} waiting requests reached).",
                    headers={"Retry-After": "5"},
                )
            if self.is_protection:
                self.limiter._protection_waiting += 1
            else:
                self.limiter._benchmark_waiting += 1
            self.queued = True

        try:
            self.acquired = self.semaphore.acquire(timeout=self.timeout)
            if not self.acquired:
                raise HTTPException(
                    status_code=429,
                    detail=f"{self.error_detail} (Wait timeout of {self.timeout}s exceeded).",
                    headers={"Retry-After": "5"},
                )
            return self
        finally:
            if self.queued:
                with self.limiter._lock:
                    if self.is_protection:
                        self.limiter._protection_waiting -= 1
                    else:
                        self.limiter._benchmark_waiting -= 1
                self.queued = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            self.semaphore.release()
            self.acquired = False


class ConcurrencyLimiter:
    """Limits concurrent in-flight requests and bounded queue waiting per process."""

    def __init__(
        self,
        protection_limit: int | None = None,
        protection_max_queue: int | None = None,
        benchmark_limit: int | None = None,
        benchmark_max_queue: int | None = None,
        queue_timeout: float | None = None,
    ):
        conf = load_config().get("limits", {})
        self.protection_limit = (
            protection_limit
            if protection_limit is not None
            else int(conf.get("protection_concurrency", 4))
        )
        self.protection_max_queue = (
            protection_max_queue
            if protection_max_queue is not None
            else int(conf.get("protection_max_queue", 8))
        )
        self.benchmark_limit = (
            benchmark_limit
            if benchmark_limit is not None
            else int(conf.get("benchmark_concurrency", 1))
        )
        self.benchmark_max_queue = (
            benchmark_max_queue
            if benchmark_max_queue is not None
            else int(conf.get("benchmark_max_queue", 2))
        )
        self.queue_timeout = (
            queue_timeout
            if queue_timeout is not None
            else float(conf.get("concurrency_queue_timeout_seconds", 5.0))
        )
        self._protection_semaphore = threading.BoundedSemaphore(self.protection_limit)
        self._benchmark_semaphore = threading.BoundedSemaphore(self.benchmark_limit)
        self._lock = threading.Lock()
        self._protection_waiting = 0
        self._benchmark_waiting = 0

    def acquire_protection(self, timeout: float | None = None) -> _SemaphoreGuard:
        to = timeout if timeout is not None else self.queue_timeout
        return _SemaphoreGuard(
            self,
            self._protection_semaphore,
            to,
            f"Protection concurrency limit reached ({self.protection_limit} active operations per process).",
            is_protection=True,
        )

    def acquire_benchmark(self, timeout: float = 2.0) -> _SemaphoreGuard:
        return _SemaphoreGuard(
            self,
            self._benchmark_semaphore,
            timeout,
            f"Benchmark concurrency limit reached ({self.benchmark_limit} active benchmark per process).",
            is_protection=False,
        )


# Global instances
rate_limiter = RateLimiter()
concurrency_limiter = ConcurrencyLimiter()
