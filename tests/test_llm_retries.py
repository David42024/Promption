"""Tests for bounded, safe retries, backoff, and Retry-After policy."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat-service"))

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.deadline import RequestDeadline
from app.llm_client import LLMClient, AIGuardBlocked
from promption.llm.exceptions import (
    LLMConfigurationError,
    LLMQuotaError,
    LLMProviderUnavailableError,
    LLMTimeoutError,
)


class MockResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self._json_data = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if not self.is_success:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_retry_on_429_then_success():
    client = LLMClient()
    client.models = [{
        "id": "openai-primary", "label": "OpenAI", "provider": "openai", "api": "openai",
        "model": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1/chat/completions",
        "temperature": 0.2, "max_tokens": 100
    }]
    client.max_attempts = 3

    calls = 0

    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return MockResponse(429, headers={"Retry-After": "0.01"})
        return MockResponse(200, json_data={"choices": [{"message": {"content": "Success after 429"}}]})

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        # Fast sleep to avoid long test delays
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = await client.generate([{"role": "user", "content": "hi"}], deadline=RequestDeadline(10.0))
            assert res.text == "Success after 429"
            assert calls == 2
            mock_sleep.assert_called()


@pytest.mark.asyncio
async def test_retry_on_503_transient_error():
    client = LLMClient()
    client.models = [{
        "id": "openai-primary", "label": "OpenAI", "provider": "openai", "api": "openai",
        "model": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1/chat/completions",
        "temperature": 0.2, "max_tokens": 100
    }]
    client.max_attempts = 3

    calls = 0

    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return MockResponse(503)
        return MockResponse(200, json_data={"choices": [{"message": {"content": "Success after 503"}}]})

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = await client.generate([{"role": "user", "content": "hi"}], deadline=RequestDeadline(10.0))
            assert res.text == "Success after 503"
            assert calls == 2
            assert res.provider_calls == 2
            assert res.fallback_count == 0
            mock_sleep.assert_called()


@pytest.mark.asyncio
async def test_no_retry_on_401_configuration_error():
    client = LLMClient()
    client.models = [{
        "id": "openai-primary", "label": "OpenAI", "provider": "openai", "api": "openai",
        "model": "gpt-4", "api_key": "invalid_key", "base_url": "https://api.openai.com/v1/chat/completions",
        "temperature": 0.2, "max_tokens": 100
    }]
    client.max_attempts = 3

    calls = 0

    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        return MockResponse(401)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(LLMConfigurationError) as exc_info:
                await client.generate([{"role": "user", "content": "hi"}], deadline=RequestDeadline(10.0))
            assert exc_info.value.status_code == 401
            assert calls == 1  # Exactly 1 call, never retried
            mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_long_retry_after_exceeds_budget_fails_early():
    client = LLMClient()
    client.models = [{
        "id": "openai-primary", "label": "OpenAI", "provider": "openai", "api": "openai",
        "model": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1/chat/completions",
        "temperature": 0.2, "max_tokens": 100
    }]
    client.max_attempts = 3

    calls = 0

    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        # Provider says wait 120 seconds, but total request deadline is only 5 seconds
        return MockResponse(429, headers={"Retry-After": "120"})

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(LLMQuotaError) as exc_info:
                await client.generate([{"role": "user", "content": "hi"}], deadline=RequestDeadline(5.0))
            assert exc_info.value.retry_after == 120.0
            # Must abort early because 120s > 5s budget, rather than clamping to an arbitrary small number
            assert calls == 1


@pytest.mark.asyncio
async def test_max_attempts_exhausted_raises_last_error():
    client = LLMClient()
    client.models = [{
        "id": "openai-primary", "label": "OpenAI", "provider": "openai", "api": "openai",
        "model": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1/chat/completions",
        "temperature": 0.2, "max_tokens": 100
    }]
    client.max_attempts = 3

    calls = 0

    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        return MockResponse(503)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(LLMProviderUnavailableError) as exc_info:
                await client.generate([{"role": "user", "content": "hi"}], deadline=RequestDeadline(10.0))
            assert calls == 3
            assert getattr(exc_info.value, "provider_calls", None) == 3


@pytest.mark.asyncio
async def test_fallback_across_candidates_accumulates_calls_and_tracks_fallback():
    client = LLMClient()
    client.models = [
        {"id": "c1", "label": "Model-1", "provider": "openai", "api": "openai",
         "model": "m1", "api_key": "k", "base_url": "http://m1", "temperature": 0.2, "max_tokens": 100},
        {"id": "c2", "label": "Model-2", "provider": "groq", "api": "groq",
         "model": "m2", "api_key": "k", "base_url": "http://m2", "temperature": 0.2, "max_tokens": 100},
    ]
    client.max_attempts = 1

    calls = 0
    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        if "http://m1" in url:
            return MockResponse(503)
        return MockResponse(200, json_data={"choices": [{"message": {"content": "Fallback success"}}]})

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await client.generate([{"role": "user", "content": "hi"}], deadline=RequestDeadline(10.0))
        assert res.text == "Fallback success"
        assert res.model == "Model-2"
        assert res.fallback_count == 1
        assert res.provider_calls == 2
        assert calls == 2


@pytest.mark.asyncio
async def test_three_attempts_two_failures_one_success_accumulates_three_calls():
    client = LLMClient()
    client.models = [{
        "id": "c1", "label": "Model-1", "provider": "openai", "api": "openai",
        "model": "m1", "api_key": "k", "base_url": "http://m1", "temperature": 0.2, "max_tokens": 100
    }]
    client.max_attempts = 3

    calls = 0
    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            return MockResponse(503)
        return MockResponse(200, json_data={"choices": [{"message": {"content": "Success on third"}}]})

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await client.generate([{"role": "user", "content": "hi"}], deadline=RequestDeadline(10.0))
            assert res.text == "Success on third"
            assert res.provider_calls == 3
            assert res.fallback_count == 0
            assert calls == 3


@pytest.mark.asyncio
async def test_security_blocked_does_not_trigger_fallback():
    client = LLMClient()
    client.models = [
        {"id": "c1", "label": "Model-1", "provider": "vercel_ai", "api": "vercel_ai",
         "model": "m1", "api_key": "k", "base_url": "http://m1", "temperature": 0.2, "max_tokens": 100},
        {"id": "c2", "label": "Model-2", "provider": "groq", "api": "groq",
         "model": "m2", "api_key": "k", "base_url": "http://m2", "temperature": 0.2, "max_tokens": 100},
    ]
    client.max_attempts = 3

    calls = 0
    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        return MockResponse(403, json_data={"code": "CONTENT_BLOCKED"})

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with pytest.raises(AIGuardBlocked):
            await client.generate([{"role": "user", "content": "attack"}], deadline=RequestDeadline(10.0))
        assert calls == 1  # Never fell back to Model-2


@pytest.mark.asyncio
async def test_tool_turn_fallback_accumulates_calls():
    client = LLMClient()
    client.models = [
        {"id": "c1", "label": "Model-1", "provider": "openai", "api": "openai",
         "model": "m1", "api_key": "k", "base_url": "http://m1", "temperature": 0.2, "max_tokens": 100},
        {"id": "c2", "label": "Model-2", "provider": "groq", "api": "groq",
         "model": "m2", "api_key": "k", "base_url": "http://m2", "temperature": 0.2, "max_tokens": 100},
    ]

    calls = 0
    async def mock_post(url, **kwargs):
        nonlocal calls
        calls += 1
        if "http://m1" in url:
            return MockResponse(503)
        return MockResponse(200, json_data={"choices": [{"message": {"content": "tool reply", "tool_calls": []}}]})

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await client.generate_tool_turn([{"role": "user", "content": "hi"}], tools=[], deadline=RequestDeadline(10.0))
        assert res["text"] == "tool reply"
        assert res["model"] == "Model-2"
        assert res["fallback_count"] == 1
        assert res["provider_calls"] == 2
        assert calls == 2
