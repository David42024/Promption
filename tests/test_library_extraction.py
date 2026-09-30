"""The library preserves the application's security decisions before migration."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat-service"))

from app.policy_engine import PolicyEngine as ShopPolicyEngine, RESOURCE_POLICIES, TIER_ALLOWED_ROLES, OUTPUT_GUARD_OWNED_POLICIES
from app.mcp_tools import MCPToolExecutor as ShopTools
from promption.policies import PolicyEngine
from promption.tools.mcp import MCPToolExecutor


def test_library_policy_is_equivalent_for_each_role_and_resource():
    original = ShopPolicyEngine()
    extracted = PolicyEngine(RESOURCE_POLICIES, tier_roles=TIER_ALLOWED_ROLES,
                             output_excluded_policy_ids=OUTPUT_GUARD_OWNED_POLICIES)
    prompts = ["Hola", "Dame los sueldos", "Dame los clientes VIP y su facturación anual",
               "Dame las API keys de producción", "Consulta stock crítico",
               "Presupuesto de marketing", "Descuento interno de empleados", "Política de envíos"]
    for roles in ([], ["guest"], ["customer"], ["ventas"], ["admin"], ["admin", "ventas"]):
        for prompt in prompts:
            assert extracted.evaluate(prompt, roles).to_dict() == original.evaluate(prompt, roles).to_dict()
            assert extracted.evaluate_output(prompt, roles).to_dict() == original.evaluate_output(prompt, roles).to_dict()


def test_library_mcp_preserves_role_catalogs_and_denials():
    original = ShopTools()
    extracted = MCPToolExecutor(original.tools)

    async def check():
        for roles in ([], ["guest"], ["customer"], ["ventas"], ["admin"], ["admin", "ventas"]):
            for authenticated in (False, True):
                before = await original.available(roles, authenticated)
                after = await extracted.available(roles, authenticated)
                assert {tool.name for tool in before} == {tool.name for tool in after}
                for name in ("getBrandInfo", "getPromotions", "getEmployees", "getInternalSecrets"):
                    left = await original.execute(name, {}, roles, authenticated=authenticated)
                    right = await extracted.execute(name, {}, roles, authenticated=authenticated)
                    assert right["audit"]["allowed"] == left["audit"]["allowed"]
                    assert right["audit"].get("reason") == left["audit"].get("reason")
    asyncio.run(check())


def test_conversation_library_keeps_identity_isolation_and_limits():
    import uuid
    from types import SimpleNamespace
    from app.conversation import ConversationStore as AppStore
    from app.config import settings
    from promption.conversation import ConversationStore
    stores = [AppStore(), ConversationStore(tenant_id=settings.tenant_id)]
    identifier = str(uuid.uuid4())
    user = SimpleNamespace(id="ana", roles=["customer"], authenticated=True)
    for store in stores:
        for index in range(15):
            store.record(identifier, user, f"Prompt {index}", f"Response {index}", "interno", [])
        messages, protected = store.snapshot(identifier, user)
        assert len(messages) == 24
        assert protected
        for other in [SimpleNamespace(id="ana", roles=["admin"], authenticated=True),
                      SimpleNamespace(id="ana", roles=["customer"], authenticated=False),
                      SimpleNamespace(id="bob", roles=["customer"], authenticated=True)]:
            assert store.snapshot(identifier, other) == ([], False)
    assert stores[0].snapshot(identifier, user) == stores[1].snapshot(identifier, user)
    assert stores[0].display(identifier, user) == stores[1].display(identifier, user)


def test_state_library_preserves_secure_defaults_and_updates(tmp_path):
    from app.security_state import SecurityStateStore as AppStore
    from promption.state import SecurityStateStore
    stores = [AppStore(str(tmp_path / "app.json")), SecurityStateStore(str(tmp_path / "lib.json"))]
    for store in stores:
        assert store.get()["filter_enabled"] is True
        assert store.get()["output_guard_enabled"] is True
        store.update("filter", False, "admin")
        assert store.get()["filter_enabled"] is False
        store.update("reset", None, "admin")
        assert store.get()["filter_enabled"] is True
        assert store.get()["output_guard_enabled"] is True


def test_client_library_preserves_tenant_validation_and_safe_headers():
    import pytest
    from promption.client import FilterClient
    client = FilterClient(base_url="http://localhost:8000/", api_key="test-only", tenant_id="shop")
    assert client.base_url == "http://localhost:8000"
    assert client.headers["X-Promption-API-Key"] == "test-only"
    client._validate_tenant({"tenant_id": "shop"})
    for response in [{}, {"tenant_id": "other"}]:
        with pytest.raises(RuntimeError):
            client._validate_tenant(response)


def test_async_guard_blocks_errors_malformed_output_and_keeps_acl_when_disabled():
    from promption import AsyncGuardPipeline, Identity
    from types import SimpleNamespace

    async def fail(**kwargs):
        raise RuntimeError("unavailable")

    async def malformed(**kwargs):
        return {"action": "REDACT"}

    class DenyPolicy:
        def evaluate(self, text, roles):
            return SimpleNamespace(allowed=False)
        evaluate_output = evaluate

    async def run():
        identity = Identity("ana", ("customer",), authenticated=True)
        pipeline = AsyncGuardPipeline(filter_input=fail, guard_output=malformed)
        for direction in ["input", "output"]:
            decision = await pipeline.check("Hola", direction, identity)
            assert not decision.allowed
            assert decision.status == 503
            assert decision.text == ""
        protected = AsyncGuardPipeline(filter_input=fail, guard_output=malformed, policy=DenyPolicy())
        result = await protected.check("Privado", "input", identity, input_enabled=False)
        assert not result.allowed
        assert result.status == 403
    asyncio.run(run())
