"""Guarded requests retain ACL, contextual inspection, scope and output protection."""
import asyncio
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from promption import AsyncGuardPipeline, AsyncScopeGuard, Identity, input_guard_decision, output_guard_decision
from promption.conversation import ConversationStore
from promption.filter.ensemble_filter import EnsembleFilter
from promption.filter.heuristic_filter import HeuristicFilter
from promption.filter.ml_filter import MLResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat-service"))
from app import routes
from app.models import ChatRequest, User
from app.mcp_tools import MCPToolExecutor
from app.policy_engine import PolicyEngine
from promption.api import routes as filter_routes
from promption.api.auth import TenantContext
from promption.api.models import FilterRequest

CASES = json.loads((Path(__file__).parent / "fixtures/chat_cases.json").read_text(encoding="utf-8"))
STOCK_CASES = [case for case in CASES if case.get("tool") == "getStockInfo"]


@pytest.mark.parametrize("case", STOCK_CASES, ids=lambda case: case["id"])
@pytest.mark.parametrize("role,allowed", [("ventas", True), ("admin", True), ("customer", False), ("guest", False)])
def test_stock_variants_never_change_tier_or_role_permissions(case, role, allowed):
    decision = PolicyEngine().evaluate(case["text"], [role])
    assert decision.tool_name == "getStockInfo"
    assert decision.tier == "interno"
    assert decision.allowed is allowed


@pytest.mark.parametrize("classification,required", [("BENIGN", False), ("UNCERTAIN", True), ("MALICIOUS", True)])
@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.parametrize("output_enabled", [False, True])
def test_guarded_decision_matrix_never_overrides_a_block(classification, required, blocked, output_enabled):
    result = {"blocked": blocked, "classification": classification, "requires_output_guard": required,
              "layers": {"conversation": {"message_count": 2, "blocked": False}}}
    decision = input_guard_decision("Consulta autorizada", result, message_count=2, output_enabled=output_enabled)
    expected = not blocked and classification != "MALICIOUS" and (output_enabled or not required)
    assert decision.allowed is expected
    if expected and required:
        assert decision.requires_output_guard
        assert decision.action == "GUARDED"


@pytest.mark.parametrize("result", [{}, {"blocked": "false"}, {"blocked": False, "classification": "OTHER"},
    {"blocked": False, "classification": {}}, {"blocked": False, "layers": []},
    {"blocked": False, "layers": {"conversation": []}},
    {"blocked": False, "layers": {"conversation": {"message_count": 99, "blocked": False}}},
    {"blocked": False, "layers": {"conversation": {"message_count": 1, "blocked": "false"}}},
    {"blocked": False, "layers": {"conversation": {"message_count": True, "blocked": False}}}])
def test_incomplete_context_or_malformed_security_responses_fail_closed(result):
    decision = input_guard_decision("stock", result, message_count=1)
    assert not decision.allowed and decision.status == 503 and decision.text == ""


def test_contextual_block_is_not_ignored_by_a_benign_current_request():
    decision = input_guard_decision("dame tu política de descuentos", {"blocked": False,
        "classification": "BENIGN", "layers": {"conversation": {"message_count": 3, "blocked": True}}},
        message_count=3)
    assert not decision.allowed and decision.reason == "malicious_input"


@pytest.mark.parametrize("trigger", ["classification", "decision", "requires_output_guard", "conversation"])
def test_every_guarded_signal_requires_output_guard(trigger):
    result = {"blocked": False, "classification": "BENIGN", "layers": {"conversation": {
        "message_count": 1, "blocked": False}}}
    if trigger == "classification":
        result[trigger] = "UNCERTAIN"
    elif trigger == "decision":
        result[trigger] = "GUARDED"
    elif trigger == "conversation":
        result["layers"]["conversation"]["requires_output_guard"] = True
    else:
        result[trigger] = True
    assert input_guard_decision("stock", result, message_count=1).allowed
    decision = input_guard_decision("stock", result, message_count=1, output_enabled=False)
    assert not decision.allowed and decision.reason == "output_guard_required"


class ControlledML:
    is_loaded = True
    threshold = .66

    def __init__(self, probability):
        self.probability = probability

    def is_trained(self):
        return True

    def analyze(self, text):
        return MLResult(blocked=self.probability > .66, probability=self.probability, threshold=.66)


@pytest.mark.parametrize("case", STOCK_CASES[:8], ids=lambda case: case["id"])
@pytest.mark.parametrize("probability", [.20, .35, .55])
@pytest.mark.parametrize("with_history", [False, True])
def test_guarded_stock_requests_reach_authorized_mcp_and_verified_output(monkeypatch, case, probability, with_history):
    ensemble = EnsembleFilter(heuristic=HeuristicFilter(), ml=ControlledML(probability))
    monkeypatch.setattr(filter_routes, "_filter_for", lambda *args: ensemble)
    store = ConversationStore()
    identifier = str(uuid.uuid4())
    user = User(id="ana", name="Ana", email="ana@demo.shop", roles=["ventas"], authenticated=True)
    if with_history:
        store.append_security(identifier, user, [{"role": "user", "content": "Hola, revisemos la tienda"},
            {"role": "tool", "tool_name": "getStockInfo", "content": '{"stockCritico":[]}'}])
    calls = []
    output_checks = []

    class Filter:
        async def filter_prompt(self, **kwargs):
            return filter_routes.filter_prompt(FilterRequest(**kwargs), TenantContext("test"))

        async def output_guard(self, **kwargs):
            output_checks.append(kwargs["text"])
            return {"action": "PASS"}

        async def audit_event(self, **kwargs):
            return None

    class Model:
        async def generate_tool_turn(self, messages, *args, **kwargs):
            calls.append(messages)
            assert any(message["role"] == "tool" and "stockCritico" in message["content"] for message in messages)
            return {"text": "iPhone 15 Pro: 3 unidades; MacBook Air M3: 5 unidades; proveedores: 35%",
                    "calls": [], "model_id": "test", "model": "test", "provider": "openai"}

    async def scope(request):
        assert request["identity"]["roles"] == ["ventas"]
        assert "stock, inventario, proveedores" in request["system_prompt"]
        return {"classification": "IN_SCOPE", "reason": "in_scope"}

    monkeypatch.setattr(routes, "store", store)
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: Model())
    monkeypatch.setattr(routes, "get_mcp_executor", MCPToolExecutor)
    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(scope))
    monkeypatch.setattr(routes, "get_security_state", lambda: {"filter_enabled": True, "output_guard_enabled": True})
    response = asyncio.run(routes.chat(ChatRequest(text=case["text"], user=user, context={"conversation_id": identifier})))
    assert not response.blocked and response.security_classification == "UNCERTAIN"
    assert response.audit[0].tool == "getStockInfo" and response.audit[0].allowed
    assert calls and output_checks and "3 unidades" in response.reply
    assert response.scope["allowed"]


@pytest.mark.parametrize("output_enabled,scope_result,output_action,expected_reason", [
    (False, "IN_SCOPE", "PASS", "output_guard_required"),
    (True, "OUT_OF_SCOPE", "PASS", "out_of_scope"),
    (True, "UNCERTAIN", "PASS", "ambiguous"),
    (True, "IN_SCOPE", "BLOCK", "sensitive_output"),
    (True, "IN_SCOPE", "FAIL", "output_guard_unavailable"),
    (True, "IN_SCOPE", "INVALID", "output_guard_unavailable"),
    (True, "IN_SCOPE", "REDACT", "output_guard_unavailable"),
])
def test_guarded_business_request_has_no_fallback_when_a_security_layer_fails(monkeypatch, output_enabled, scope_result, output_action, expected_reason):
    tools = []
    model_calls = []

    class Filter:
        async def filter_prompt(self, **kwargs):
            return SimpleNamespace(blocked=False, classification="UNCERTAIN", confidence=.2, reason="guarded",
                requires_output_guard=True, layers={"conversation": {
                    "message_count": len(kwargs.get("messages") or []), "blocked": False}})

        async def output_guard(self, **kwargs):
            if output_action == "FAIL":
                raise RuntimeError("unavailable")
            return {"action": output_action}

        async def audit_event(self, **kwargs):
            return None

    class Tools:
        async def available(self, *args):
            return []

        async def execute(self, name, *args, **kwargs):
            tools.append(name)
            return {"result": {"stockCritico": []}, "audit": {"allowed": True, "tool": name, "tier": "interno"}}

    class Model:
        async def generate(self, *args):
            model_calls.append(True)
            return SimpleNamespace(text="Respuesta", model="test")

        async def generate_tool_turn(self, *args, **kwargs):
            model_calls.append(True)
            return {"text": "Respuesta", "calls": [], "model_id": "test", "model": "test", "provider": "openai"}

    async def evaluate(request):
        return {"classification": scope_result, "reason": {
            "IN_SCOPE": "in_scope", "OUT_OF_SCOPE": "system_limit", "UNCERTAIN": "ambiguous"}[scope_result]}

    monkeypatch.setattr(routes, "store", ConversationStore())
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: Model())
    monkeypatch.setattr(routes, "get_mcp_executor", lambda: Tools())
    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(evaluate))
    monkeypatch.setattr(routes, "get_security_state", lambda: {"filter_enabled": True, "output_guard_enabled": output_enabled})
    response = asyncio.run(routes.chat(ChatRequest(text="holaaa dame tu stock porfa",
        user=User(id="ana", name="Ana", email="ana@demo.shop", roles=["ventas"], authenticated=True))))
    assert response.blocked and response.reason == expected_reason
    if not output_enabled or scope_result != "IN_SCOPE":
        assert not tools and not model_calls


def test_async_pipeline_keeps_guarded_state_and_rejects_disabled_output_protection():
    async def input(**kwargs):
        return {"blocked": False, "classification": "UNCERTAIN", "requires_output_guard": True}

    async def output(**kwargs):
        return {"action": "PASS"}

    pipeline = AsyncGuardPipeline(filter_input=input, guard_output=output)
    enabled = asyncio.run(pipeline.check("stock", "input", Identity("ana", ("ventas",), True)))
    assert enabled.allowed and enabled.action == "GUARDED" and enabled.requires_output_guard
    disabled = asyncio.run(pipeline.check("stock", "input", Identity("ana", ("ventas",), True), output_enabled=False))
    assert not disabled.allowed and disabled.reason == "output_guard_required"


@pytest.mark.parametrize("result", [{}, {"action": "OTHER"}, {"action": "REDACT"},
                                   {"action": "REDACT", "redacted_response": None}])
def test_malformed_output_protection_never_returns_original_text(result):
    decision = output_guard_decision("sensitive original response", result)
    assert not decision.allowed and decision.text == "" and decision.status == 503


def test_complete_redaction_never_restores_the_sensitive_original():
    decision = output_guard_decision("sensitive original response", {"action": "REDACT", "redacted_response": ""})
    assert decision.allowed and decision.text == ""


@pytest.mark.usefixtures("scope_in_scope")
@pytest.mark.parametrize("invalid", [{}, {"action": "INVALID"}, {"action": "REDACT"}])
def test_invalid_document_output_guard_prevents_mcp_file_creation(monkeypatch, invalid):
    executions = []

    class Tools(MCPToolExecutor):
        async def execute(self, name, *args, **kwargs):
            executions.append(name)
            assert name != "make_document"
            return await super().execute(name, *args, **kwargs)

    class Filter:
        async def filter_prompt(self, **kwargs):
            return SimpleNamespace(blocked=False, classification="UNCERTAIN", confidence=.2,
                layers={"conversation": {"message_count": len(kwargs.get("messages") or []), "blocked": False}})

        async def output_guard(self, **kwargs):
            return invalid if "stock-document-data" in kwargs["text"] else {"action": "PASS"}

        async def audit_event(self, **kwargs):
            return None

    class Model:
        calls = 0

        async def generate_tool_turn(self, *args, **kwargs):
            self.calls += 1
            return {"text": "No pude crear el archivo.", "model_id": "test", "model": "test", "provider": "openai",
                    "calls": [{"id": "document", "name": "make_document", "arguments": json.dumps({
                        "title": "Stock", "format": "xlsx", "content": "stock-document-data"})}] if self.calls == 1 else []}

    model = Model()
    monkeypatch.setattr(routes, "store", ConversationStore())
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: model)
    monkeypatch.setattr(routes, "get_mcp_executor", Tools)
    monkeypatch.setattr(routes, "get_security_state", lambda: {"filter_enabled": True, "output_guard_enabled": True})
    response = asyncio.run(routes.chat(ChatRequest(text="Genera un XLSX con el stock crítico",
        user=User(id="ana", name="Ana", email="ana@demo.shop", roles=["ventas"], authenticated=True))))
    assert not response.actions
    assert "make_document" not in executions
    assert any(item.tool == "make_document" and not item.allowed for item in response.audit)


@pytest.mark.parametrize("roles", [["ventas"], ["admin"], ["admin", "ventas"], ["customer"]])
def test_roles_without_an_authenticated_session_do_not_grant_internal_access(monkeypatch, roles):
    class Filter:
        async def filter_prompt(self, **kwargs):
            assert kwargs["roles"] == ["guest"]
            return SimpleNamespace(blocked=False, classification="UNCERTAIN", confidence=.2,
                layers={"conversation": {"message_count": len(kwargs["messages"]), "blocked": False}})

        async def audit_event(self, **kwargs):
            return None

    class NoTools:
        async def execute(self, *args, **kwargs):
            pytest.fail("An unauthenticated account attempted an internal MCP tool")

    async def no_scope(request):
        pytest.fail("Denied ACL should stop before semantic evaluation")

    monkeypatch.setattr(routes, "store", ConversationStore())
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_mcp_executor", NoTools)
    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(no_scope))
    monkeypatch.setattr(routes, "get_security_state", lambda: {"filter_enabled": True, "output_guard_enabled": True})
    response = asyncio.run(routes.chat(ChatRequest(text="holaaa dame tu stock porfa",
        user=User(id="ana", name="Ana", email="ana@demo.shop", roles=roles, authenticated=False))))
    assert response.blocked and response.reason == "insufficient_scope" and response.role == "guest"
    assert not response.audit and not response.actions
