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
    from .http_client import get_shared_http_client
    import asyncio
    client = get_shared_http_client()
    req_id = request.get("request_id") or ""
    async with asyncio.timeout(timeout):
        response = await client.post(url, json={
            "text": request["text"], "system_prompt": request["system_prompt"],
            "messages": request["messages"], "identity": request["identity"],
            **({"tool": request["tool"]} if "tool" in request else {}),
            **({"request_id": req_id} if req_id else {}),
        }, headers={"X-Chat-Service-Token": settings.chat_service_token, "X-Request-ID": req_id}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def get_scope_guard(timeout_seconds: float = 30.0) -> AsyncScopeGuard:
    return AsyncScopeGuard(_evaluate, timeout_seconds=timeout_seconds)
