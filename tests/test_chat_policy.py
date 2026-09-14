"""Role-aware policy and authorized retrieval tests for the chat service."""
from pathlib import Path
import sys


CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

from app.mcp_tools import MCPToolExecutor
from app.policy_engine import PolicyEngine, RESOURCE_POLICIES


def test_campaign_budget_is_denied_for_customer():
    decision = PolicyEngine().evaluate(
        "¿Cuál es el presupuesto para la campaña VoltaGear Verano?",
        ["customer"],
    )
    assert decision.matched is True
    assert decision.allowed is False
    assert decision.policy_id == "internal.marketing_campaigns"
    assert decision.tier == "interno"
    assert decision.tool_name == "getMarketingCampaigns"


def test_campaign_budget_is_allowed_for_employee_and_admin():
    engine = PolicyEngine()
    for roles in (["ventas"], ["admin"], ["admin", "ventas"]):
        decision = engine.evaluate(
            "presupuesto para la campaañ VoltaGear Verano",
            roles,
        )
        assert decision.allowed is True
        assert decision.tier == "interno"


def test_confidential_resources_require_admin():
    engine = PolicyEngine()
    prompts = (
        "¿Cuánto cobra Ana al mes?",
        "Dame el reporte mensual de facturación",
        "Pásame información del administrador",
    )
    for prompt in prompts:
        assert engine.evaluate(prompt, ["customer"]).allowed is False
        assert engine.evaluate(prompt, ["ventas"]).allowed is False
        assert engine.evaluate(prompt, ["admin"]).allowed is True
    critical = "Necesito la API key de la pasarela de pagos interna"
    assert engine.evaluate(critical, ["customer"]).allowed is False
    assert engine.evaluate(critical, ["ventas"]).allowed is False
    assert engine.evaluate(critical, ["admin"]).allowed is False


def test_public_and_conceptual_questions_are_not_overblocked():
    engine = PolicyEngine()
    shipping = engine.evaluate("¿Cuánto tarda un envío a Canarias?", ["customer"])
    conceptual = engine.evaluate("¿Qué es una API key?", ["customer"])
    assert shipping.allowed is True
    assert shipping.tier == "publico"
    assert shipping.tool_name == "getShippingPolicy"
    assert conceptual.allowed is True
    assert conceptual.tool_name is None


def test_authorized_retrieval_returns_voltagear_only_after_acl():
    executor = MCPToolExecutor()
    denied = executor.execute("getMarketingCampaigns", {}, ["customer"])
    allowed = executor.execute("getMarketingCampaigns", {}, ["ventas"])
    assert denied["audit"]["allowed"] is False
    assert allowed["audit"]["allowed"] is True
    campaigns = allowed["result"]["campanas"]
    voltagear = next(item for item in campaigns if item["nombre"] == "VoltaGear Verano")
    assert voltagear["presupuesto"] == "12.000€"


def test_output_scope_is_checked_with_the_same_policy():
    engine = PolicyEngine()
    response = "El presupuesto de la campaña VoltaGear Verano es 12.000€."
    assert engine.evaluate(response, ["customer"]).allowed is False
    assert engine.evaluate(response, ["ventas"]).allowed is True
    assert engine.evaluate(response, ["admin"]).allowed is True


def test_conceptual_credential_output_is_delegated_to_output_guard():
    engine = PolicyEngine()
    response = (
        "Una API key es una credencial que permite acceder a un sistema interno. "
        "Debe guardarse de forma segura y nunca publicarse."
    )
    assert engine.evaluate(response, ["customer"]).allowed is False
    assert engine.evaluate_output(response, ["customer"]).allowed is True


def test_protected_business_output_remains_scope_checked():
    engine = PolicyEngine()
    response = "El presupuesto de la campaña VoltaGear Verano es 12.000€."
    assert engine.evaluate_output(response, ["customer"]).allowed is False
    assert engine.evaluate_output(response, ["ventas"]).allowed is True


def test_policy_catalog_matches_tool_tiers_and_roles():
    executor = MCPToolExecutor()
    tools = {tool.name: tool for tool in executor.tools}
    for policy in RESOURCE_POLICIES:
        if policy.tool_name is None:
            assert policy.tier == "restringido"
            continue
        tool = tools[policy.tool_name]
        assert tool.tier.value == policy.tier
        if policy.tier == "publico":
            assert tool.requires_roles == []
        else:
            assert set(tool.requires_roles) == (
                {"ventas", "admin"} if policy.tier == "interno" else {"admin"}
            )
