"""Application transport for the reusable semantic scope guard."""
from urllib.parse import urljoin
from contextvars import ContextVar

import httpx

from promption import AsyncScopeGuard
from .config import settings
from .capabilities import is_capabilities_question, is_simple_greeting


_scope_request = ContextVar("shop_scope_request", default=None)


def begin_scope_request(request_id: str, *, tenant_id: str = "", conversation_id: str = ""):
    """Start a request-local receipt collection, never shared across conversations."""
    _scope_request.set({"request_id": request_id, "tenant_id": tenant_id,
                        "conversation_id": conversation_id, "receipts": [], "system_prompt": None})


def scope_bridge_context() -> dict:
    """Return only the current request's verification evidence for the trusted bridge."""
    context = _scope_request.get()
    if not context:
        return {}
    return {"scope_receipts": list(context["receipts"]),
            "scope_system_prompt": context["system_prompt"],
            "scope_binding": {key: context[key] for key in ("request_id", "tenant_id", "conversation_id")}}


def collect_scope_receipts(data: dict):
    """Collect opaque proofs; only the signing bridge can validate their contents."""
    context = _scope_request.get()
    if not context or not isinstance(data, dict):
        return
    receipts = data.get("scope_receipts", [])
    if isinstance(receipts, list):
        safe = [item for item in receipts[:32] if isinstance(item, str) and len(item) <= 4096]
        context["receipts"][:] = (context["receipts"] + safe)[-32:]


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
    context = _scope_request.get()
    req_id = context["request_id"] if context else request.get("request_id") or ""
    if context:
        context["system_prompt"] = request["system_prompt"]
    async with asyncio.timeout(timeout):
        response = await client.post(url, json={
            "text": request["text"], "system_prompt": request["system_prompt"],
            "messages": request["messages"], "identity": request["identity"],
            **({"tool": request["tool"]} if "tool" in request else {}),
            **({"request_id": req_id} if req_id else {}),
            "timeout_ms": max(1, int(timeout * 1000) - min(250, int(timeout * 100))),
            **(scope_bridge_context() if context else {}),
        }, headers={"X-Chat-Service-Token": settings.chat_service_token, "X-Request-ID": req_id}, timeout=timeout)
    try:
        data = response.json()
    except (ValueError, TypeError):
        return {"classification": "UNCERTAIN", "reason": "invalid_scope_response", "provider_calls": 0}
    if not isinstance(data, dict):
        return {"classification": "UNCERTAIN", "reason": "invalid_scope_response", "provider_calls": 0}
    if response.status_code >= 400:
        allowed_error_reasons = {"scope_unavailable", "scope_timeout", "scope_truncated", "invalid_scope_response"}
        return {**data, "classification": "UNCERTAIN",
                "reason": data.get("reason") if data.get("reason") in allowed_error_reasons else "scope_unavailable"}
    if context and data.get("classification") == "IN_SCOPE" and data.get("reason") == "in_scope":
        receipt = data.get("scope_receipt")
        if isinstance(receipt, str) and len(receipt) <= 4096:
            context["receipts"][:] = (context["receipts"] + [receipt])[-32:]
    return data


def get_scope_guard(timeout_seconds: float = 30.0) -> AsyncScopeGuard:
    return AsyncScopeGuard(_evaluate, timeout_seconds=timeout_seconds)
