"""Typed LLM exception hierarchy with sanitized attributes and no raw bodies."""
from __future__ import annotations

from typing import Any


def parse_retry_after(header_val: str | None) -> float | None:
    """Parses a Retry-After header value into seconds (supports delta-seconds and HTTP-date)."""
    if not header_val:
        return None
    val = str(header_val).strip()
    try:
        return max(0.0, float(val))
    except ValueError:
        pass
    try:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = (dt - now).total_seconds()
        return max(0.0, diff)
    except Exception:
        return None


class LLMError(Exception):
    """Base exception for all LLM client and bridge failures."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        status_code: int | None = None,
        code: str = "LLM_ERROR",
        retryable: bool = False,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.model = model
        self.provider = provider
        self.status_code = status_code
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.model:
            parts.append(f"(model={self.model})")
        if self.status_code:
            parts.append(f"(status={self.status_code})")
        return " ".join(parts)


class LLMConfigurationError(LLMError):
    """Configuration error (missing API key, invalid model, authentication 401/403)."""

    def __init__(
        self,
        message: str = "LLM configuration or authentication error",
        *,
        model: str | None = None,
        provider: str | None = None,
        status_code: int | None = 401,
        code: str = "CONFIGURATION_ERROR",
    ):
        super().__init__(
            message,
            model=model,
            provider=provider,
            status_code=status_code,
            code=code,
            retryable=False,
        )


class LLMTimeoutError(LLMError):
    """Timeout error (request timeout or global monotonic deadline exceeded)."""

    def __init__(
        self,
        message: str = "LLM request timed out",
        *,
        model: str | None = None,
        provider: str | None = None,
        code: str = "TIMEOUT",
    ):
        super().__init__(
            message,
            model=model,
            provider=provider,
            status_code=504,
            code=code,
            retryable=True,
        )


class LLMConnectivityError(LLMError):
    """Network connection failure, DNS resolution failure, connection refused/reset."""

    def __init__(
        self,
        message: str = "Failed to connect to LLM provider",
        *,
        model: str | None = None,
        provider: str | None = None,
        code: str = "CONNECTIVITY_ERROR",
    ):
        super().__init__(
            message,
            model=model,
            provider=provider,
            status_code=503,
            code=code,
            retryable=True,
        )


class LLMQuotaError(LLMError):
    """Rate limit or quota exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str = "LLM rate limit or quota exceeded",
        *,
        model: str | None = None,
        provider: str | None = None,
        retry_after: float | None = None,
        code: str = "QUOTA_EXCEEDED",
    ):
        super().__init__(
            message,
            model=model,
            provider=provider,
            status_code=429,
            code=code,
            retryable=True,
            retry_after=retry_after,
        )


class LLMProviderUnavailableError(LLMError):
    """Provider downtime or upstream server failure (5xx)."""

    def __init__(
        self,
        message: str = "LLM provider is temporarily unavailable",
        *,
        model: str | None = None,
        provider: str | None = None,
        status_code: int | None = 503,
        code: str = "PROVIDER_UNAVAILABLE",
    ):
        super().__init__(
            message,
            model=model,
            provider=provider,
            status_code=status_code,
            code=code,
            retryable=True,
        )


class LLMInvalidResponseError(LLMError):
    """Empty response, malformed JSON, schema mismatch, or unexpected truncation."""

    def __init__(
        self,
        message: str = "LLM returned an invalid or empty response",
        *,
        model: str | None = None,
        provider: str | None = None,
        truncated: bool = False,
        code: str = "INVALID_RESPONSE",
    ):
        super().__init__(
            message,
            model=model,
            provider=provider,
            status_code=502,
            code=code,
            retryable=False,
        )
        self.truncated = truncated
