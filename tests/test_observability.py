import asyncio
from pathlib import Path
import sys

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

import pytest
from app import routes
from app.conversation import ConversationStore
from app.models import ChatRequest, User, UserRole


class MockFilterClient:
    async def filter_prompt(self, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(
            blocked=False,
            classification="BENIGN",
            layers={"conversation": {"message_count": len(kwargs.get("messages") or []), "blocked": False}},
            reason="",
            confidence=0.1,
        )

    async def output_guard(self, **kwargs):
        return {"action": "PASS"}

    async def audit_event(self, **kwargs):
        return None


class MockLLMClient:
    def __init__(self):
        self.last_deadline = None

    async def generate(self, messages, deadline=None):
        from app.models import LLMResponse
        return LLMResponse(
            text="Respuesta exitosa",
            model="openai-primary",
            latency_ms=120.0,
            ok=True,
            requested_model="openai-primary",
            fallback_count=0,
            fallback_reason=None,
            prompt_tokens=25,
            completion_tokens=10,
            total_tokens=35,
        )


@pytest.mark.asyncio
async def test_request_id_and_execution_metrics_propagated(monkeypatch):
    monkeypatch.setattr(routes, "store", ConversationStore())
    monkeypatch.setattr(routes, "get_filter_client", lambda: MockFilterClient())
    monkeypatch.setattr(routes, "get_llm_client", lambda: MockLLMClient())
    monkeypatch.setattr(routes, "get_security_state", lambda: {"filter_enabled": True, "output_guard_enabled": True})

    user = User(id="u123", name="Alice", email="alice@test.com", roles=[UserRole.GUEST], authenticated=False)
    custom_req_id = "req-custom-abc-123"
    req = ChatRequest(text="hola", user=user, context={"request_id": custom_req_id})

    resp = await routes.chat(req)
    assert not resp.blocked
    assert resp.request_id == custom_req_id
    assert resp.execution_metrics is not None
    metrics = resp.execution_metrics
    assert metrics["request_id"] == custom_req_id
    assert metrics["requested_model"] == "openai-primary"
    assert metrics["effective_model"] == "openai-primary"
    assert metrics["fallback_count"] == 0
    assert metrics["fallback_reason"] is None
    assert metrics["prompt_tokens"] == 25
    assert metrics["completion_tokens"] == 10
    assert metrics["total_tokens"] == 35
    assert metrics["filter_status"] == "executed"
    assert metrics["output_guard_status"] == "executed"
    assert metrics["total_latency_ms"] > 0


@pytest.mark.asyncio
async def test_missing_tokens_remain_none_not_zero(monkeypatch):
    class NoTokensLLMClient:
        async def generate(self, messages, deadline=None):
            from app.models import LLMResponse
            return LLMResponse(
                text="Respuesta sin tokens",
                model="local-model",
                latency_ms=50.0,
                ok=True,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
            )

    monkeypatch.setattr(routes, "store", ConversationStore())
    monkeypatch.setattr(routes, "get_filter_client", lambda: MockFilterClient())
    monkeypatch.setattr(routes, "get_llm_client", lambda: NoTokensLLMClient())
    monkeypatch.setattr(routes, "get_security_state", lambda: {"filter_enabled": False, "output_guard_enabled": False})

    user = User(id="u456", name="Bob", email="bob@test.com", roles=[UserRole.GUEST], authenticated=False)
    req = ChatRequest(text="hola", user=user)

    resp = await routes.chat(req)
    assert not resp.blocked
    assert resp.request_id is not None
    metrics = resp.execution_metrics
    assert metrics["prompt_tokens"] is None
    assert metrics["completion_tokens"] is None
    assert metrics["total_tokens"] is None
    assert metrics["filter_status"] == "skipped"
    assert metrics["output_guard_status"] == "skipped"
