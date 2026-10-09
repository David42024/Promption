import asyncio
import inspect
from pathlib import Path
import sys

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

import pytest
from app.config import Settings, validate_chat_service_configuration
from app.deadline import RequestDeadline
from app.llm_client import LLMClient
from app.models import ChatRequest, LLMResponse, User, UserRole
from app import routes


def test_invalid_budget_configuration_rejected():
    # Negative or too low budgets
    s1 = Settings(chat_service_token="test", max_tool_turns=0)
    with pytest.raises(ValueError, match="max_tool_turns"):
        validate_chat_service_configuration(s1, is_test=True)

    s2 = Settings(chat_service_token="test", max_tool_calls_per_turn=0)
    with pytest.raises(ValueError, match="max_tool_calls_per_turn"):
        validate_chat_service_configuration(s2, is_test=True)

    s3 = Settings(chat_service_token="test", token_budget_chat=50)
    with pytest.raises(ValueError, match="token_budget_chat"):
        validate_chat_service_configuration(s3, is_test=True)

    s4 = Settings(chat_service_token="test", token_budget_tools=50)
    with pytest.raises(ValueError, match="token_budget_tools"):
        validate_chat_service_configuration(s4, is_test=True)

    s5 = Settings(chat_service_token="test", max_context_chars=500)
    with pytest.raises(ValueError, match="max_context_chars"):
        validate_chat_service_configuration(s5, is_test=True)


def test_valid_budget_configuration_accepted():
    s = Settings(
        chat_service_token="test",
        max_tool_turns=3,
        max_tool_calls_per_turn=4,
        token_budget_chat=2000,
        token_budget_scope=500,
        token_budget_tools=4000,
        max_context_chars=50000,
    )
    validate_chat_service_configuration(s, is_test=True)
    assert s.max_tool_turns == 3
    assert s.token_budget_chat == 2000


@pytest.mark.asyncio
async def test_llm_client_records_fallback_with_cause():
    class DummyFailingClient:
        def __init__(self):
            self.calls = 0

        async def post(self, url, **kwargs):
            self.calls += 1
            if self.calls == 1:
                class FailResp:
                    is_success = False
                    status_code = 500
                    def raise_for_status(self):
                        raise RuntimeError("Server error")
                    def json(self):
                        return {}
                return FailResp()
            class SuccessResp:
                is_success = True
                status_code = 200
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"text": "Respuesta recuperada tras fallback", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
            return SuccessResp()

    llm = LLMClient(client=DummyFailingClient())
    llm.models = [
        {"id": "m1", "label": "Model Primary", "provider": "openai", "api": "vercel_ai", "base_url": "http://test1", "model": "m1", "temperature": 0.2, "max_tokens": 500},
        {"id": "m2", "label": "Model Fallback", "provider": "openai", "api": "vercel_ai", "base_url": "http://test2", "model": "m2", "temperature": 0.2, "max_tokens": 500},
    ]

    resp = await llm.generate([{"role": "user", "content": "hola"}], deadline=RequestDeadline(10.0))
    assert resp.ok is True
    assert resp.model == "Model Fallback"
    assert resp.requested_model == "Model Primary"
    assert resp.fallback_count == 1
    assert "Model Primary" in str(resp.fallback_reason)
    assert resp.total_tokens is None
    assert resp.known_usage["total_tokens"] == 15
    assert resp.provider_calls == 2
    assert resp.failed_calls == 1
    assert resp.usage_coverage["calls_without_usage"] == 1


@pytest.mark.asyncio
async def test_llm_client_detects_truncation_on_finish_reason():
    class DummyTruncatedClient:
        async def post(self, url, **kwargs):
            class TruncatedResp:
                is_success = True
                status_code = 200
                def raise_for_status(self):
                    pass
                def json(self):
                    return {
                        "text": "Texto incompleto por límite...",
                        "finishReason": "length",
                        "usage": {"prompt_tokens": 20, "completion_tokens": 100, "total_tokens": 120}
                    }
            return TruncatedResp()

    llm = LLMClient(client=DummyTruncatedClient())
    llm.models = [
        {"id": "m1", "label": "Model Test", "provider": "openai", "api": "vercel_ai", "base_url": "http://test", "model": "m1", "temperature": 0.2, "max_tokens": 100},
    ]

    resp = await llm.generate([{"role": "user", "content": "genera un texto muy largo"}], deadline=RequestDeadline(10.0))
    assert resp.ok is True
    assert resp.truncated is True


@pytest.mark.asyncio
async def test_excessive_context_rejected_cleanly(monkeypatch):
    from app.conversation import ConversationStore
    monkeypatch.setattr(routes, "store", ConversationStore())
    user = User(id="user1", name="Test", email="test@test.com", roles=[UserRole.CUSTOMER], authenticated=True)
    # Huge message exceeding max_context_chars
    huge_text = "A" * 90000
    req = ChatRequest(text=huge_text, user=user)

    resp = await routes.chat(req)
    assert resp.blocked is True
    assert resp.reason == "context_too_large"
    assert "excede el límite" in resp.reply
