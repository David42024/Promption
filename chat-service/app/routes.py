"""API routes for Chat Service"""
import hmac
import json
import logging
import time
from typing import List
from fastapi import APIRouter, Depends, Header, HTTPException, status

from .config import settings
from .models import (
    ChatRequest, ChatResponse, HealthResponse, MCPToolCall, PolicyInfo, UserRole
)
from .filter_client import get_filter_client
from .llm_client import get_llm_client
from .mcp_tools import get_mcp_executor
from .policy_engine import (
    RESOURCE_POLICIES,
    TIER_ALLOWED_ROLES,
    authorization_message,
    get_policy_engine,
)
from .lib.shop import SECRET_MARKERS, build_system_prompt

router = APIRouter()
logger = logging.getLogger(__name__)

_start_time = time.time()


def _primary_role(user_roles: List[str]) -> str:
    """Return the most privileged canonical role for response metadata."""
    for role in ("admin", "ventas", "customer", "guest"):
        if role in user_roles:
            return role
    return "guest"


def require_trusted_client(
    x_chat_service_token: str | None = Header(default=None),
) -> None:
    """Require the server-to-server token when configured."""
    expected = settings.chat_service_token
    if expected and not (
        x_chat_service_token
        and hmac.compare_digest(x_chat_service_token, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid chat service credentials",
        )


def _contains_secret(text: str) -> bool:
    """Check if text contains secret markers"""
    for marker in SECRET_MARKERS:
        if isinstance(marker, str):
            if marker.lower() in text.lower():
                return True
        elif hasattr(marker, 'search'):  # regex pattern
            if marker.search(text.lower()):
                return True
    return False


@router.get("/health", tags=["system"])
async def health() -> HealthResponse:
    """Health check endpoint"""
    filter_client = get_filter_client()
    llm_client = get_llm_client()
    
    filter_connected = await filter_client.check_health()
    llm_connected = await llm_client.check_health()
    
    return HealthResponse(
        service=settings.service_name,
        status="ok" if filter_connected else "degraded",
        version=settings.version,
        filter_api_connected=filter_connected,
        llm_connected=llm_connected,
        uptime_seconds=time.time() - _start_time
    )


@router.get("/status", tags=["system"])
async def status():
    """Detailed status endpoint"""
    filter_client = get_filter_client()
    llm_client = get_llm_client()
    
    return {
        "service": settings.service_name,
        "version": settings.version,
        "uptime_seconds": time.time() - _start_time,
        "filter_api": {
            "url": settings.filter_api_url,
            "connected": await filter_client.check_health()
        },
        "llm": {
            "default_model": settings.default_model,
            "providers_available": len(llm_client.models),
            "providers": [model["provider"] for model in llm_client.models],
            "connected": await llm_client.check_health(),
            "provider_timeout_seconds": llm_client.provider_timeout,
            "total_timeout_seconds": llm_client.total_timeout,
            "max_attempts": llm_client.max_attempts,
        },
        "config": {
            "tenant_id": settings.tenant_id,
            "debug": settings.debug,
            "trusted_client_required": bool(settings.chat_service_token),
        },
        "policy_engine": {
            "enabled": True,
            "policies": len(RESOURCE_POLICIES),
            "tiers": list(TIER_ALLOWED_ROLES),
        }
    }


@router.post("/chat", tags=["chat"], dependencies=[Depends(require_trusted_client)])
async def chat(request: ChatRequest) -> ChatResponse:
    """Main chat endpoint with filtering and LLM integration"""
    
    # Convert user roles to strings
    user_roles = [
        (role.value if isinstance(role, UserRole) else str(role)).strip().lower()
        for role in request.user.roles
    ]
    primary_role = _primary_role(user_roles)
    
    # Initialize clients
    filter_client = get_filter_client()
    llm_client = get_llm_client()
    mcp_executor = get_mcp_executor()
    policy_engine = get_policy_engine()
    
    # 1. Input Filter
    filter_enabled = True  # Could be made configurable
    filter_skipped = False
    filter_result = None
    security_classification = "UNCERTAIN"
    
    if filter_enabled:
        try:
            filter_result = await filter_client.filter_prompt(
                text=request.text,
                user_id=request.user.id,
                roles=user_roles,
                use_ml=True  # Usar ML ligero (TF-IDF + LogisticRegression) que funciona en Render free
            )
            security_classification = filter_result.classification
            
            if filter_result.blocked:
                return ChatResponse(
                    blocked=True,
                    reply=f"Bloqueado por el filtro ({filter_result.reason})",
                    filter_enabled=filter_enabled,
                    filter_skipped=False,
                    role=primary_role,
                    filter_layers=filter_result.layers,
                    reason=filter_result.reason,
                    confidence=filter_result.confidence,
                    block_type="attack",
                    security_classification="MALICIOUS",
                )
        except Exception:
            logger.exception("Filter API unavailable")
            return ChatResponse(
                blocked=True,
                reply="El servicio de seguridad no está disponible. El chat se bloqueó de forma preventiva.",
                filter_enabled=filter_enabled,
                filter_skipped=True,
                role=primary_role,
                reason="Filter API unavailable",
                confidence=1.0,
                block_type="filter_unavailable",
                security_classification="UNCERTAIN",
            )

    policy_decision = policy_engine.evaluate(request.text, user_roles)
    policy_info = PolicyInfo(**policy_decision.to_dict())
    if not policy_decision.allowed:
        logger.warning(
            "Authorization denied user=%s roles=%s policy=%s tier=%s resource=%s",
            request.user.id,
            user_roles,
            policy_decision.policy_id,
            policy_decision.tier,
            policy_decision.resource,
        )
        return ChatResponse(
            blocked=True,
            reply=authorization_message(policy_decision),
            filter_enabled=filter_enabled,
            filter_skipped=filter_skipped,
            role=primary_role,
            filter_layers=filter_result.layers if filter_result else None,
            reason="insufficient_scope",
            confidence=policy_decision.confidence,
            block_type="authorization",
            policy=policy_info,
            security_classification=security_classification,
        )

    if security_classification == "UNCERTAIN" and policy_decision.tier in {
        "interno",
        "confidencial",
    }:
        logger.warning(
            "Security review required user=%s roles=%s policy=%s tier=%s",
            request.user.id,
            user_roles,
            policy_decision.policy_id,
            policy_decision.tier,
        )
        return ChatResponse(
            blocked=True,
            reply=(
                "La solicitud pide información protegida, pero el filtro no pudo "
                "clasificarla con suficiente confianza. Reformúlala de manera directa."
            ),
            filter_enabled=filter_enabled,
            filter_skipped=filter_skipped,
            role=primary_role,
            filter_layers=filter_result.layers if filter_result else None,
            reason="security_review_required",
            confidence=filter_result.confidence if filter_result else None,
            block_type="security_review",
            policy=policy_info,
            security_classification=security_classification,
        )

    audit: List[MCPToolCall] = []
    authorized_context = None
    if policy_decision.tool_name:
        tool_response = mcp_executor.execute(policy_decision.tool_name, {}, user_roles)
        tool_audit = tool_response.get("audit", {})
        audit.append(MCPToolCall(
            tool=tool_audit.get("tool", policy_decision.tool_name),
            allowed=bool(tool_audit.get("allowed", False)),
            reason=tool_audit.get("reason"),
            tier=tool_audit.get("tier", policy_decision.tier),
        ))
        if not tool_audit.get("allowed", False):
            logger.error(
                "Retrieval ACL denied after policy allow user=%s tool=%s roles=%s",
                request.user.id,
                policy_decision.tool_name,
                user_roles,
            )
            return ChatResponse(
                blocked=True,
                reply=authorization_message(policy_decision),
                audit=audit,
                filter_enabled=filter_enabled,
                filter_skipped=filter_skipped,
                role=primary_role,
                filter_layers=filter_result.layers if filter_result else None,
                reason="retrieval_acl_denied",
                confidence=1.0,
                block_type="authorization",
                policy=policy_info,
                security_classification=security_classification,
            )
        authorized_context = tool_response.get("result")

    system_prompt = build_system_prompt({
        "name": request.user.name,
        "id": request.user.id,
        "roles": user_roles,
        "authenticated": request.user.authenticated
    })
    
    # 3. Prepare messages for LLM
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    if authorized_context is not None:
        messages.append({
            "role": "system",
            "content": (
                "CONTEXTO RECUPERADO Y AUTORIZADO POR ACL. Responde únicamente con los "
                "datos relevantes de este contexto; no inventes valores ni amplíes el scope.\n"
                f"Recurso: {policy_decision.resource}\n"
                f"Tier autorizado: {policy_decision.tier}\n"
                f"Datos: {json.dumps(authorized_context, ensure_ascii=False)}"
            ),
        })
    messages.append({"role": "user", "content": request.text})
    
    # 4. Call LLM
    try:
        llm_response = await llm_client.generate(messages)
        
        reply = llm_response.text
        
    except Exception:
        logger.exception("All LLM providers failed")
        return ChatResponse(
            blocked=False,
            reply="No pude procesar tu solicitud en este momento. Inténtalo nuevamente en unos segundos.",
            filter_enabled=filter_enabled,
            filter_skipped=filter_skipped,
            role=primary_role,
            audit=audit,
            policy=policy_info,
            reason="llm_unavailable",
            security_classification=security_classification,
        )
    
    # 5. Output Guard
    output_guard_enabled = True
    output_guard_skipped = False
    guard_result = None
    
    if output_guard_enabled:
        try:
            guard_result = await filter_client.output_guard(
                text=reply,
                user_id=request.user.id,
                roles=user_roles
            )
            
            if guard_result.get("action") == "BLOCK":
                return ChatResponse(
                    blocked=True,
                    reply="No puedo mostrar información sensible o credenciales en la respuesta.",
                    guard="BLOCK",
                    filter_enabled=filter_enabled,
                    output_guard_enabled=output_guard_enabled,
                    filter_skipped=filter_skipped,
                    output_guard_skipped=False,
                    role=primary_role,
                    reason="sensitive_output",
                    confidence=float(guard_result.get("risk", 1.0)),
                    block_type="output_guard",
                    audit=audit,
                    policy=policy_info,
                    security_classification=security_classification,
                )
            
            if guard_result.get("action") == "REDACT" and guard_result.get("redacted_response"):
                reply = guard_result["redacted_response"]
                
        except Exception:
            logger.exception("Output guard unavailable")
            return ChatResponse(
                blocked=True,
                reply="La respuesta no pudo validarse y fue bloqueada de forma preventiva.",
                guard="UNAVAILABLE",
                filter_enabled=filter_enabled,
                output_guard_enabled=output_guard_enabled,
                filter_skipped=filter_skipped,
                output_guard_skipped=True,
                role=primary_role,
                reason="output_guard_unavailable",
                confidence=1.0,
                block_type="output_guard",
                audit=audit,
                policy=policy_info,
                security_classification=security_classification,
            )

    output_policy = policy_engine.evaluate_output(reply, user_roles)
    if not output_policy.allowed:
        logger.error(
            "Output scope violation user=%s roles=%s policy=%s tier=%s",
            request.user.id,
            user_roles,
            output_policy.policy_id,
            output_policy.tier,
        )
        return ChatResponse(
            blocked=True,
            reply="La respuesta contenía información fuera de tu alcance y fue bloqueada.",
            guard="BLOCK",
            filter_enabled=filter_enabled,
            output_guard_enabled=output_guard_enabled,
            filter_skipped=filter_skipped,
            output_guard_skipped=False,
            role=primary_role,
            reason="output_scope_violation",
            confidence=output_policy.confidence,
            block_type="output_guard",
            audit=audit,
            policy=PolicyInfo(**output_policy.to_dict()),
            security_classification=security_classification,
        )
    
    # 6. Check for secret leakage
    leaked = _contains_secret(reply)
    
    # 7. Add warning if filter was disabled
    if not filter_enabled:
        reply += "\n\n⚠️ (Nota del sistema: esta respuesta ha sido generada SIN filtro de entrada ni output guard. En producción, el filtro está activado y este contenido habría sido bloqueado.)"
    
    return ChatResponse(
        blocked=False,
        reply=reply,
        leaked=leaked,
        guard=guard_result.get("action", "SKIPPED") if guard_result else "SKIPPED",
        filter_enabled=filter_enabled,
        output_guard_enabled=output_guard_enabled,
        filter_skipped=filter_skipped,
        output_guard_skipped=output_guard_skipped,
        role=primary_role,
        model=llm_response.model,
        filter_layers=filter_result.layers if filter_result else None,
        audit=audit,
        policy=policy_info,
        security_classification=security_classification,
    )


@router.post("/tools/execute", tags=["tools"], dependencies=[Depends(require_trusted_client)])
async def execute_tool(
    tool_name: str,
    args: dict,
    user_roles: List[str]
):
    """Execute an MCP tool with role-based access control"""
    mcp_executor = get_mcp_executor()
    
    result = mcp_executor.execute(tool_name, args, user_roles)
    
    return result
