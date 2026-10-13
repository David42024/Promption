"""Integration checks for V8 least-privilege tool exposure."""
import asyncio

import pytest

from test_chat_capabilities import Filter, configure, request
from app import routes
from app.mcp_tools import MCPToolExecutor


@pytest.mark.usefixtures("scope_in_scope")
@pytest.mark.parametrize("arguments", ["{}", '{"limit": 2}'])
def test_prefetched_tool_not_offered_or_executed_again(monkeypatch, arguments):
    client = Filter()
    configure(monkeypatch, client)
    executor = MCPToolExecutor()
    original = executor.execute
    reads = []

    async def execute(name, args, roles, **kwargs):
        reads.append((name, args))
        return await original(name, args, roles, **kwargs)

    monkeypatch.setattr(executor, "execute", execute)
    monkeypatch.setattr(routes, "get_mcp_executor", lambda: executor)

    class Model:
        turn = 0

        async def generate_tool_turn(self, messages, tools, model_id=None):
            names = {item["function"]["name"] for item in tools}
            assert "getCatalogSummary" not in names
            assert not names.intersection({"getEmployees", "getVIPClients", "getStockInfo"})
            self.turn += 1
            return {
                "model": "test", "model_id": "test", "provider": "openai",
                "text": "Catálogo público disponible." if self.turn > 1 else "",
                "calls": [] if self.turn > 1 else [{
                    "id": "unadvertised-read", "name": "getCatalogSummary",
                    "arguments": arguments,
                }],
            }

    monkeypatch.setattr(routes, "get_llm_client", Model)
    result = asyncio.run(routes.chat(request("customer", "Resume el catálogo público de la tienda.")))
    assert sum(name == "getCatalogSummary" for name, _ in reads) == 1
    assert any(item.tool == "getCatalogSummary" and not item.allowed for item in result.audit)
    assert result.actions == []
    assert not result.blocked and result.guard == "PASS"
    assert result.eval_counts["scope"] >= 1
    assert client.outputs == [result.reply]
