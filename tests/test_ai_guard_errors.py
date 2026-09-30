"""Security denials from the AI SDK bridge must never trigger a model fallback."""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat-service"))
from app import llm_client


@pytest.mark.parametrize("method", ["generate", "generate_tool_turn"])
@pytest.mark.parametrize("status,code", [(403, "OUT_OF_SCOPE"), (503, "SCOPE_UNCERTAIN"),
                                       (403, "CONTENT_BLOCKED")])
def test_bridge_guard_denial_propagates_without_retry(monkeypatch, method, status, code):
    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            calls.append(url)
            assert len(calls) == 1
            return httpx.Response(status, json={"code": code,
                "scope": {"classification": "OUT_OF_SCOPE", "reason": "system_limit"}},
                request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", Client)
    client = llm_client.LLMClient()
    client.models = [{"id": name, "label": name, "provider": "openai", "api": "vercel_ai",
        "model": "test", "base_url": "http://bridge.test/turn", "max_tokens": 900,
        "temperature": 0.2} for name in ("primary", "fallback")]
    messages = [{"role": "user", "content": "Consulta comercial"}]
    coroutine = client.generate(messages) if method == "generate" else client.generate_tool_turn(messages, [])
    with pytest.raises(llm_client.AIGuardBlocked) as error:
        asyncio.run(coroutine)
    assert error.value.code == code
    assert len(calls) == 1
