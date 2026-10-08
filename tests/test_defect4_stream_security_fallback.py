"""Regression test for Defect 4 Python client fallback behavior on CONTENT_BLOCKED vs MODEL_UNAVAILABLE."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
import pytest

CHAT_SERVICE_DIR = Path(__file__).resolve().parent.parent / "chat-service"
if str(CHAT_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE_DIR))

from app.llm_client import LLMClient, AIGuardBlocked
from promption.llm.exceptions import LLMProviderUnavailableError


def test_python_client_does_not_fallback_on_content_blocked():
    """A 403 CONTENT_BLOCKED from the bridge must immediately raise AIGuardBlocked without triggering fallback to secondary models."""
    client = LLMClient()
    mock_candidates = [
        {"id": "cand-1", "label": "Model Primary", "provider": "primary", "api": "vercel_ai", "base_url": "http://bridge/turn", "model": "primary", "max_tokens": 1000, "temperature": 0.2, "api_key": "test"},
        {"id": "cand-2", "label": "Model Fallback", "provider": "fallback", "api": "vercel_ai", "base_url": "http://bridge/turn", "model": "fallback", "max_tokens": 1000, "temperature": 0.2, "api_key": "test"},
    ]

    request_calls = []

    async def mock_post(c, url, json=None, headers=None, timeout=None):
        request_calls.append(json.get("model"))
        # Returns 403 CONTENT_BLOCKED
        req = httpx.Request("POST", url)
        return httpx.Response(
            403,
            request=req,
            json={"error": "Promption bloqueó la respuesta", "code": "CONTENT_BLOCKED", "reason": "sensitive_output"},
        )

    client.models = mock_candidates
    with patch("app.llm_client._post_http", side_effect=mock_post):
        with pytest.raises(AIGuardBlocked) as exc_info:
            asyncio.run(client.generate_tool_turn([{"role": "user", "content": "test"}], []))

        assert exc_info.value.code == "CONTENT_BLOCKED"
        # Only the first candidate was called; no fallback took place!
        assert len(request_calls) == 1
        assert request_calls[0] == "primary"


def test_python_client_falls_back_on_actual_provider_unavailable():
    """An actual 503 MODEL_UNAVAILABLE triggers fallback to candidate 2."""
    client = LLMClient()
    mock_candidates = [
        {"id": "cand-1", "label": "Model Primary", "provider": "primary", "api": "vercel_ai", "base_url": "http://bridge/turn", "model": "primary", "max_tokens": 1000, "temperature": 0.2, "api_key": "test"},
        {"id": "cand-2", "label": "Model Fallback", "provider": "fallback", "api": "vercel_ai", "base_url": "http://bridge/turn", "model": "fallback", "max_tokens": 1000, "temperature": 0.2, "api_key": "test"},
    ]

    request_calls = []

    async def mock_post(c, url, json=None, headers=None, timeout=None):
        model = json.get("model")
        request_calls.append(model)
        req = httpx.Request("POST", url)
        if model == "primary":
            return httpx.Response(503, request=req, json={"error": "Service unavailable", "code": "MODEL_UNAVAILABLE"})
        else:
            return httpx.Response(200, request=req, json={"text": "Fallback response", "calls": [], "finish_reason": "stop"})

    client.models = mock_candidates
    with patch("app.llm_client._post_http", side_effect=mock_post):
        res = asyncio.run(client.generate_tool_turn([{"role": "user", "content": "test"}], []))
        assert res["text"] == "Fallback response"
        assert len(request_calls) == 2
        assert request_calls == ["primary", "fallback"]


def test_python_client_does_not_fallback_on_guard_unavailable():
    """A 503 GUARD_UNAVAILABLE from the bridge must immediately raise AIGuardBlocked and NOT trigger fallback."""
    client = LLMClient()
    mock_candidates = [
        {"id": "cand-1", "label": "Model Primary", "provider": "primary", "api": "vercel_ai", "base_url": "http://bridge/turn", "model": "primary", "max_tokens": 1000, "temperature": 0.2, "api_key": "test"},
        {"id": "cand-2", "label": "Model Fallback", "provider": "fallback", "api": "vercel_ai", "base_url": "http://bridge/turn", "model": "fallback", "max_tokens": 1000, "temperature": 0.2, "api_key": "test"},
    ]

    request_calls = []

    async def mock_post(c, url, json=None, headers=None, timeout=None):
        request_calls.append(json.get("model"))
        req = httpx.Request("POST", url)
        return httpx.Response(
            503,
            request=req,
            json={"error": "Output guard unavailable", "code": "GUARD_UNAVAILABLE"},
        )

    client.models = mock_candidates
    with patch("app.llm_client._post_http", side_effect=mock_post):
        with pytest.raises(AIGuardBlocked) as exc_info:
            asyncio.run(client.generate_tool_turn([{"role": "user", "content": "test"}], []))

        assert exc_info.value.code == "GUARD_UNAVAILABLE"
        assert len(request_calls) == 1
        assert request_calls[0] == "primary"
