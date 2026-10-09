"""Regression tests reproducing Defect B (zero provider calls on blocked generation)
and Defect C (partial token usage tracking with known_usage and usage_coverage).
"""
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
import pytest

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

from app.models import ChatRequest, User, UserRole
from app.llm_client import AIGuardBlocked
from app import routes

pytestmark = pytest.mark.usefixtures("scope_in_scope")


def _make_req(text: str, user_id: str = "u-defect-bc", role: str = "customer") -> ChatRequest:
    return ChatRequest(
        text=text,
        user=User(
            id=user_id,
            name="Tester B and C",
            email="tester@promption.test",
            roles=[UserRole(role)],
            authenticated=True,
        ),
        context={"conversation_id": str(uuid.uuid4())},
    )


class MockFilter:
    def __init__(self, blocked: bool = False):
        self.blocked = blocked

    async def filter_prompt(self, text, identity, use_ml=True, messages=None, timeout=None):
        from promption.api.models import FilterResponse
        return FilterResponse(
            text=text,
            decision="BLOCKED" if self.blocked else "ALLOWED",
            blocked=self.blocked,
            confidence=0.9 if self.blocked else 0.1,
            latency_ms=1.5,
            reason="injection_detected" if self.blocked else "benign",
            layers={"conversation": {"message_count": len(messages) if messages else 1, "blocked": self.blocked}},
            sanitized="" if self.blocked else text,
            classification="MALICIOUS" if self.blocked else "BENIGN",
            requires_review=self.blocked,
            requires_output_guard=not self.blocked,
        )

    async def output_guard(self, text, identity=None, timeout=None):
        return {
            "action": "PASS",
            "text": text,
            "risk": 0.05,
            "findings": [],
        }

    async def audit_event(self, **kwargs):
        return None


class MockLLMBlockedZeroCalls:
    def __init__(self):
        self.models = [{"id": "gpt-4o", "label": "gpt-4o", "provider": "mock"}]

    async def generate(self, messages, deadline=None):
        # Simulates AIGuardBlocked with 0 provider calls (e.g. blocked before reaching provider)
        raise AIGuardBlocked("CONTENT_BLOCKED", scope=None, provider_calls=0)

    async def generate_tool_turn(self, messages, tool_specs=None, model_id=None, force_tool=None, deadline=None):
        raise AIGuardBlocked("CONTENT_BLOCKED", scope=None, provider_calls=0)


class MockLLMWithUsage:
    def __init__(self, prompt_tokens=20, completion_tokens=10, total_tokens=30, reasoning_tokens=None, calls=1):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.reasoning_tokens = reasoning_tokens
        self.calls = calls
        self.models = [{"id": "gpt-4o", "label": "gpt-4o", "provider": "mock"}]

    async def generate(self, messages, deadline=None):
        return SimpleNamespace(
            text="Respuesta con tokens conocidos",
            model="gpt-4o",
            requested_model="gpt-4o",
            provider_calls=self.calls,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
            reasoning_tokens=self.reasoning_tokens,
            fallback_count=0,
            fallback_reason=None,
            latency_ms=10.0,
        )

    async def generate_tool_turn(self, messages, tool_specs=None, model_id=None, force_tool=None, deadline=None):
        return {
            "text": "Respuesta con tokens conocidos",
            "calls": [],
            "model": "gpt-4o",
            "model_id": "gpt-4o",
            "requested_model": "gpt-4o",
            "provider_calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "fallback_count": 0,
            "fallback_reason": None,
        }


@pytest.mark.asyncio
async def test_reproduce_defect_b_zero_provider_calls_preserves_zero(monkeypatch):
    """Defect B: AIGuardBlocked with provider_calls=0 must NOT increment generation_calls or failed_calls."""
    flt = MockFilter(blocked=False)
    llm = MockLLMBlockedZeroCalls()

    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("Hola, prueba de bloqueo sin llamadas")
    res = await routes.chat(req)

    assert res.blocked is True
    assert res.block_type == "model_guard"
    metrics = res.execution_metrics
    assert metrics is not None
    # Crucial check: Must be 0, NOT 1!
    assert metrics["generation_calls"] == 0
    assert metrics["failed_calls"] == 0
    assert metrics["stages"]["generation"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_reproduce_defect_c_partial_usage_identifies_subtotal_and_null_total(monkeypatch):
    """Defect C: 1 scope call without usage + 1 gen call with 30 tokens -> total_tokens is None, known_usage has 30."""
    from promption import AsyncScopeGuard

    async def mock_scope_without_usage(request):
        return {
            "classification": "IN_SCOPE",
            "reason": "in_scope",
            "model": "scope-model",
            "provider_calls": 1,
            "usage": None,
        }

    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(mock_scope_without_usage))
    flt = MockFilter(blocked=False)
    llm = MockLLMWithUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30, calls=1)

    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("Consulta tienda")
    res = await routes.chat(req)

    assert res.blocked is False
    metrics = res.execution_metrics
    assert metrics["scope_calls"] == 1
    assert metrics["generation_calls"] == 1
    assert metrics["provider_calls"] == 2

    # Defect C check: total_tokens must be None (incomplete), NOT 30!
    assert metrics["total_tokens"] is None
    assert metrics["prompt_tokens"] is None
    assert metrics["completion_tokens"] is None

    # Known usage must identify the 30 tokens from generation:
    assert metrics["known_usage"]["total_tokens"] == 30
    assert metrics["known_usage"]["prompt_tokens"] == 20
    assert metrics["known_usage"]["completion_tokens"] == 10

    # Coverage must show incomplete:
    assert metrics["usage_coverage"]["is_complete"] is False
    assert metrics["usage_coverage"]["calls_total"] == 2
    assert metrics["usage_coverage"]["calls_with_usage"] == 1
    assert metrics["usage_coverage"]["calls_without_usage"] == 1


@pytest.mark.asyncio
async def test_complete_usage_aggregates_both_calls(monkeypatch):
    """When all calls have known usage, total_tokens is complete and equals sum of scope + generation."""
    from promption import AsyncScopeGuard

    async def mock_scope_with_usage(request):
        return {
            "classification": "IN_SCOPE",
            "reason": "in_scope",
            "model": "scope-model",
            "provider_calls": 1,
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 15,
                "total_tokens": 30,
                "reasoning_tokens": 2,
            },
        }

    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(mock_scope_with_usage))
    flt = MockFilter(blocked=False)
    llm = MockLLMWithUsage(prompt_tokens=15, completion_tokens=15, total_tokens=30, reasoning_tokens=0, calls=1)

    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("Consulta tienda completa")
    res = await routes.chat(req)

    assert res.blocked is False
    metrics = res.execution_metrics
    assert metrics["scope_calls"] == 1
    assert metrics["generation_calls"] == 1
    assert metrics["provider_calls"] == 2

    assert metrics["total_tokens"] == 60
    assert metrics["prompt_tokens"] == 30
    assert metrics["completion_tokens"] == 30
    assert metrics["reasoning_tokens"] == 2

    assert metrics["known_usage"]["total_tokens"] == 60
    assert metrics["usage_coverage"]["is_complete"] is True
    assert metrics["usage_coverage"]["calls_total"] == 2
    assert metrics["usage_coverage"]["calls_with_usage"] == 2
    assert metrics["usage_coverage"]["calls_without_usage"] == 0
