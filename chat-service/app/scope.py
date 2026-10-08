"""Application transport for the reusable semantic scope guard."""
from urllib.parse import urljoin

import httpx

from promption import AsyncScopeGuard
from .config import settings
from .capabilities import is_capabilities_question, is_simple_greeting


async def _evaluate(request: dict) -> dict:
    if "tool" not in request and (is_capabilities_question(request["text"]) or is_simple_greeting(request["text"])):
        return {"classification": "IN_SCOPE", "reason": "in_scope"}
    if not settings.vercel_ai_url or not settings.chat_service_token:
        raise RuntimeError("Scope classifier is not configured")
    timeout = float(request.get("timeout") or 30.0)
    url = urljoin(settings.vercel_ai_url, "scope")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.post(url, json={
            "text": request["text"], "system_prompt": request["system_prompt"],
            "messages": request["messages"], "identity": request["identity"],
            **({"tool": request["tool"]} if "tool" in request else {}),
        }, headers={"X-Chat-Service-Token": settings.chat_service_token})
        response.raise_for_status()
        return response.json()


def get_scope_guard(timeout_seconds: float = 30.0) -> AsyncScopeGuard:
    return AsyncScopeGuard(_evaluate, timeout_seconds=timeout_seconds)
