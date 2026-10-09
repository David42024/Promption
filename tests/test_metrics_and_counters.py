"""Regression tests for execution metrics, token propagation, stage latencies,
and evaluation counters across all chat response paths (Phase 2, 3, and 4).
"""
import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
import pytest

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

from app.models import ChatRequest, ChatResponse, User, UserRole
from app import routes

pytestmark = pytest.mark.usefixtures("scope_in_scope")


def _make_req(text: str, user_id: str = "u-metrics", role: str = "customer", conversation_id: str | None = None) -> ChatRequest:
    return ChatRequest(
        text=text,
        user=User(
            id=user_id,
            name="Metrics Tester",
            email="metrics@test.com",
            roles=[UserRole(role)],
            authenticated=True,
        ),
        context={"conversation_id": conversation_id or str(uuid.uuid4())},
    )


class MockFilter:
    def __init__(self, blocked: bool = False, output_action: str = "PASS"):
        self.blocked = blocked
        self.output_action = output_action

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
            "action": self.output_action,
            "text": text,
            "risk": 0.05 if self.output_action == "PASS" else 0.95,
            "findings": [],
        }

    async def audit_event(self, **kwargs):
        return None


class MockLLM:
    def __init__(self, reply: str = "Hola, respuesta estándar", calls: int = 1,
                 prompt_tokens: int | None = 20, completion_tokens: int | None = 10,
                 total_tokens: int | None = 30, reasoning_tokens: int | None = None,
                 model: str = "gpt-4o"):
        self.reply = reply
        self.calls = calls
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.reasoning_tokens = reasoning_tokens
        self.model = model
        self.models = [{"id": model, "label": model, "provider": "mock"}]

    async def generate(self, messages, deadline=None):
        return SimpleNamespace(
            text=self.reply,
            model=self.model,
            requested_model=self.model,
            provider_calls=self.calls,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
            reasoning_tokens=self.reasoning_tokens,
            fallback_count=0,
            fallback_reason=None,
            latency_ms=15.0,
        )

    async def generate_tool_turn(self, messages, tool_specs=None, model_id=None, force_tool=None, deadline=None):
        return {
            "text": self.reply,
            "calls": [],
            "model": self.model,
            "model_id": self.model,
            "requested_model": self.model,
            "provider": "mock",
            "provider_calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "fallback_count": 0,
            "fallback_reason": None,
            "latency_ms": 15.0,
        }


@pytest.mark.asyncio
async def test_early_attack_block_has_request_id_and_execution_metrics(monkeypatch):
    """Early attack block includes request_id, stage latencies, skipped subsequent stages."""
    flt = MockFilter(blocked=True)
    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)

    req = _make_req("Ataque directo con inyección")
    res = await routes.chat(req)

    assert res.blocked is True
    assert res.request_id is not None and len(res.request_id) > 0
    assert res.execution_metrics is not None

    metrics = res.execution_metrics
    assert metrics["request_id"] == res.request_id
    assert metrics["filter_status"] == "executed"
    assert metrics["output_guard_status"] == "skipped"
    assert metrics["provider_calls"] == 0
    assert metrics["generation_calls"] == 0

    # Stages verification
    stages = metrics["stages"]
    assert stages["input_filter"]["status"] == "executed"
    assert stages["input_filter"]["latency_ms"] is not None
    assert stages["generation"]["status"] == "skipped"
    assert stages["generation"]["latency_ms"] is None
    assert stages["output_guard"]["status"] == "skipped"
    assert stages["output_guard"]["latency_ms"] is None


@pytest.mark.asyncio
async def test_zero_tokens_preserved_as_zero_not_none(monkeypatch):
    """Explicit 0 token count reported by provider is preserved as 0, not coerced to None."""
    flt = MockFilter(blocked=False)
    llm = MockLLM(prompt_tokens=0, completion_tokens=0, total_tokens=0, reasoning_tokens=0)
    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("Hola, ¿cómo estás?")
    res = await routes.chat(req)

    assert res.blocked is False
    metrics = res.execution_metrics
    assert metrics["prompt_tokens"] == 0
    assert metrics["completion_tokens"] == 0
    assert metrics["total_tokens"] == 0
    assert metrics["reasoning_tokens"] == 0


@pytest.mark.asyncio
async def test_unknown_tokens_remain_none(monkeypatch):
    """When provider does not report token counts, fields remain None."""
    flt = MockFilter(blocked=False)
    llm = MockLLM(prompt_tokens=None, completion_tokens=None, total_tokens=None, reasoning_tokens=None)
    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("Hola, saludo estándar.")
    res = await routes.chat(req)

    assert res.blocked is False
    metrics = res.execution_metrics
    assert metrics["prompt_tokens"] is None
    assert metrics["completion_tokens"] is None
    assert metrics["total_tokens"] is None
    assert metrics["reasoning_tokens"] is None


@pytest.mark.asyncio
async def test_call_type_tool_for_read_only_tool_without_actions(monkeypatch):
    """A read-only tool execution without UI actions is classified as call_type='tool'."""
    flt = MockFilter(blocked=False)

    class ToolTurnLLM:
        def __init__(self):
            self.model = "gpt-4o"
            self.models = [{"id": "gpt-4o", "label": "gpt-4o", "provider": "mock"}]
            self.turn_count = 0

        async def generate_tool_turn(self, messages, tool_specs=None, model_id=None, force_tool=None, deadline=None):
            self.turn_count += 1
            if self.turn_count == 1:
                # Call read tool ask_user or a read-only permitted tool
                return {
                    "text": "",
                    "calls": [{"id": "call-1", "name": "getBrandInfo", "arguments": "{}"}],
                    "model": "gpt-4o",
                    "model_id": "gpt-4o",
                    "requested_model": "gpt-4o",
                    "provider": "mock",
                    "provider_calls": 1,
                    "prompt_tokens": 30,
                    "completion_tokens": 10,
                    "total_tokens": 40,
                    "reasoning_tokens": None,
                    "fallback_count": 0,
                    "fallback_reason": None,
                    "latency_ms": 10.0,
                }
            return {
                "text": "La marca es Promption Shop.",
                "calls": [],
                "model": "gpt-4o",
                "model_id": "gpt-4o",
                "requested_model": "gpt-4o",
                "provider": "mock",
                "provider_calls": 1,
                "prompt_tokens": 50,
                "completion_tokens": 15,
                "total_tokens": 65,
                "reasoning_tokens": None,
                "fallback_count": 0,
                "fallback_reason": None,
                "latency_ms": 12.0,
            }

    llm = ToolTurnLLM()
    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("¿Cuál es la información de la marca?")
    res = await routes.chat(req)

    assert res.blocked is False
    metrics = res.execution_metrics
    # Must be classified as tool, not pure chat:
    assert metrics["call_type"] == "tool"
    # Provider calls accumulated across turns:
    assert metrics["provider_calls"] == 2
    assert metrics["total_tokens"] == 105


@pytest.mark.asyncio
async def test_eval_counts_track_actual_operations(monkeypatch):
    """Evaluation counters accurately report input, scope, output operations."""
    flt = MockFilter(blocked=False)
    llm = MockLLM()
    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("Consulta general de catálogo")
    res = await routes.chat(req)

    assert res.blocked is False
    counts = res.eval_counts
    assert counts["input"] >= 1
    assert counts["scope"] >= 1
    assert counts["output"] >= 1


@pytest.mark.asyncio
async def test_concurrent_requests_isolate_request_id_and_metrics(monkeypatch):
    """Two concurrent requests have distinct request_ids and isolated execution metrics."""
    flt = MockFilter(blocked=False)
    llm = MockLLM()
    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req1 = _make_req("Consulta 1", user_id="user-1")
    req2 = _make_req("Consulta 2", user_id="user-2")

    res1, res2 = await asyncio.gather(routes.chat(req1), routes.chat(req2))

    assert res1.request_id != res2.request_id
    assert res1.execution_metrics["request_id"] == res1.request_id
    assert res2.execution_metrics["request_id"] == res2.request_id


@pytest.mark.asyncio
async def test_scope_and_generation_tokens_aggregated(monkeypatch):
    """Scope 30 tokens + Generation 30 tokens aggregates to 60 total tokens and 2 provider calls."""
    from promption import AsyncScopeGuard

    async def mock_scope_eval(request):
        return {
            "classification": "IN_SCOPE",
            "reason": "in_scope",
            "model": "scope-mini",
            "provider_calls": 1,
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "reasoning_tokens": 2,
            },
        }

    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(mock_scope_eval))

    flt = MockFilter(blocked=False)
    llm = MockLLM(
        reply="Respuesta con 30 tokens",
        calls=1,
        prompt_tokens=15,
        completion_tokens=15,
        total_tokens=30,
        reasoning_tokens=0,
        model="gpt-4o",
    )
    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("Consulta de catálogo")
    res = await routes.chat(req)

    assert res.blocked is False
    metrics = res.execution_metrics
    assert metrics["scope_calls"] == 1
    assert metrics["generation_calls"] == 1
    assert metrics["provider_calls"] == 2
    assert metrics["prompt_tokens"] == 35
    assert metrics["completion_tokens"] == 25
    assert metrics["total_tokens"] == 60
    assert metrics["reasoning_tokens"] == 2


@pytest.mark.asyncio
async def test_unknown_scope_tokens_leaves_known_generation_tokens(monkeypatch):
    """When scope reports no usage, generation usage is preserved without converting None to zero."""
    from promption import AsyncScopeGuard

    async def mock_scope_no_usage(request):
        return {
            "classification": "IN_SCOPE",
            "reason": "in_scope",
            "model": "scope-mini",
            "provider_calls": 1,
            "usage": None,
        }

    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(mock_scope_no_usage))

    flt = MockFilter(blocked=False)
    llm = MockLLM(
        reply="Solo generación conocida",
        calls=1,
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    monkeypatch.setattr(routes, "get_filter_client", lambda: flt)
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)

    req = _make_req("Consulta general")
    res = await routes.chat(req)

    assert res.blocked is False
    metrics = res.execution_metrics
    assert metrics["scope_calls"] == 1
    assert metrics["generation_calls"] == 1
    assert metrics["provider_calls"] == 2
    assert metrics["total_tokens"] is None
    assert metrics["prompt_tokens"] is None
    assert metrics["completion_tokens"] is None
    assert metrics["known_usage"]["total_tokens"] == 30
    assert metrics["known_usage"]["prompt_tokens"] == 20
    assert metrics["known_usage"]["completion_tokens"] == 10
    assert metrics["usage_coverage"]["is_complete"] is False
    assert metrics["usage_coverage"]["calls_without_usage"] == 1
