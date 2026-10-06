"""Business tool catalog backed by the official MCP Python SDK."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional

from anyio import to_process

from .runtime import make_document

from mcp.server import MCPServer


class Tier(str, Enum):
    PUBLICO = "publico"
    INTERNO = "interno"
    CONFIDENCIAL = "confidencial"


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    description: str
    tier: Tier
    requires_roles: List[str]
    handler: Callable[..., Dict[str, Any]]
    guest_read: bool = False


async def mcp_make_document(title: str, content: str,
                            format: Literal["txt", "csv", "pdf", "docx", "xlsx"]) -> dict[str, Any]:
    """Run document creation in a cancellable server worker process."""
    return await to_process.run_sync(make_document, title, content, format, cancellable=True)


class MCPToolExecutor:
    """Keep role policy outside the SDK and delegate tool mechanics to MCPServer."""

    def __init__(self, policies: List[ToolPolicy], *, roles=("admin", "ventas", "customer", "guest"),
                 name: str = "Promption", require_authentication: bool = True):
        self.tools = list(policies)
        self.roles = roles
        self.require_authentication = require_authentication
        self._policies = {tool.name: tool for tool in self.tools}
        
        # We use a single server for all tools to dynamically compute the union of available tools
        self.server = MCPServer(name, version="1.0.0")
        for policy in self.tools:
            self.server.add_tool(policy.handler, name=policy.name,
                                 description=policy.description,
                                 structured_output=True)

    async def available(self, roles: List[str], authenticated: bool):
        if self.require_authentication and not authenticated and "guest" not in roles:
            return []
            
        all_tools = await self.server.list_tools()
        return [tool for tool in all_tools if self._permitted(self._policies[tool.name], roles, authenticated)]

    def _permitted(self, policy: ToolPolicy, roles: List[str], authenticated: bool) -> bool:
        if "guest" in roles or (not authenticated and not self.require_authentication):
            return (policy.guest_read and policy.tier == Tier.PUBLICO
                    and not policy.requires_roles)
        return (authenticated and (not policy.requires_roles
                or bool(set(policy.requires_roles).intersection(roles))))

    async def execute(self, tool_name: str, args: Dict[str, Any],
                      user_roles: List[str], authenticated: bool = True) -> dict[str, Any]:
        policy = self._policies.get(tool_name)
        audit = {"tool": tool_name, "tier": policy.tier.value if policy else "unknown",
                 "roles": user_roles, "allowed": False,
                 "at": datetime.now(timezone.utc).isoformat()}
        if policy is None:
            audit["reason"] = "tool desconocida"
            return {"result": {"error": "Tool desconocida"}, "audit": audit}
        
        if not self._permitted(policy, user_roles, authenticated):
            audit["reason"] = "sesión o rol insuficiente"
            return {"result": {"error": "Permiso denegado"}, "audit": audit}
            
        try:
            result = await self.server.call_tool(tool_name, args or {})
            if result.is_error or result.structured_content is None:
                raise ValueError("La herramienta no devolvió un resultado válido")
        except Exception:
            audit["reason"] = "error de ejecución"
            return {"result": {"error": "La herramienta no pudo ejecutarse"},
                    "audit": audit}
        audit["allowed"] = True
        return {"result": result.structured_content, "audit": audit}

