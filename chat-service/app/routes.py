"""API routes for Chat Service"""
import time
from typing import List
from fastapi import APIRouter, HTTPException, status

from .config import settings
from .models import (
    ChatRequest, ChatResponse, HealthResponse, ErrorResponse,
    UserRole
)
from .filter_client import get_filter_client
from .llm_client import get_llm_client
from .mcp_tools import get_mcp_executor

# Import shop utilities locally to avoid circular import
try:
    from .lib.shop import build_system_prompt, SECRET_MARKERS
except ImportError:
    # Fallback for development
    SECRET_MARKERS = [
        "EMPLEADO-25", "vip1@correo.com", "CLI-VIP-", "pk_live_", "sk_live_"
    ]
    
    def build_system_prompt(user):
        roles = user.get("roles", [])
        is_admin = "admin" in roles
        scope = "TODO" if is_admin else "PÚBLICO"
        return f"Eres asistente de Promption Shop. Usuario: {user.get('name')}, Scope: {scope}"

router = APIRouter()

_start_time = time.time()


def _is_admin(user_roles: List[str]) -> bool:
    """Check if user has admin role"""
    return UserRole.ADMIN.value in user_roles


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


def _basic_local_filter(text: str) -> tuple[bool, str]:
    """Basic local filter as fallback when Filter API is unavailable
    
    Returns: (blocked, reason)
    """
    # Palabras clave sospechosas para prompt injection
    suspicious_keywords = [
        "token", "clave", "password", "secret", "credencial", "api key",
        "admin secret", "jwt", "sesión", "autenticación", "olvida tus instrucciones",
        "ignore the policies", "override", "jailbreak", "desactivar el filtro"
    ]
    
    text_lower = text.lower()
    
    # Detectar petición directa de credenciales
    if any(keyword in text_lower for keyword in suspicious_keywords):
        return True, "petición de credenciales o información sensible"
    
    # Detectar intento de jailbreak
    jailbreak_patterns = [
        "olvida", "ignora", "desactiva", "override", "modo desarrollador",
        "actuar sin restricciones", "simular que eres", "ahora eres"
    ]
    
    if any(pattern in text_lower for pattern in jailbreak_patterns):
        return True, "intento de jailbreak o override de políticas"
    
    return False, ""


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
            "connected": await llm_client.check_health()
        },
        "config": {
            "tenant_id": settings.tenant_id,
            "debug": settings.debug
        }
    }


@router.post("/chat", tags=["chat"])
async def chat(request: ChatRequest) -> ChatResponse:
    """Main chat endpoint with filtering and LLM integration"""
    
    # Convert user roles to strings
    user_roles = [role.value if isinstance(role, UserRole) else role for role in request.user.roles]
    is_admin = _is_admin(user_roles)
    
    # Initialize clients
    filter_client = get_filter_client()
    llm_client = get_llm_client()
    mcp_executor = get_mcp_executor()
    
    # 1. Input Filter
    filter_enabled = True  # Could be made configurable
    filter_skipped = False
    filter_result = None
    
    if filter_enabled:
        try:
            filter_result = await filter_client.filter_prompt(
                text=request.text,
                user_id=request.user.id,
                roles=user_roles,
                use_ml=True
            )
            
            if filter_result.blocked:
                return ChatResponse(
                    blocked=True,
                    reply=f"Bloqueado por el filtro ({filter_result.reason})",
                    filter_enabled=filter_enabled,
                    filter_skipped=False,
                    role="admin" if is_admin else "ventas",
                    filter_layers=filter_result.layers,
                    reason=filter_result.reason,
                    confidence=filter_result.confidence
                )
        except Exception as e:
            print(f"Filter API error: {e}, using local fallback filter")
            filter_skipped = True
            # Usar filtro local básico como fallback
            local_blocked, local_reason = _basic_local_filter(request.text)
            if local_blocked:
                return ChatResponse(
                    blocked=True,
                    reply=f"Bloqueado por el filtro local ({local_reason})",
                    filter_enabled=filter_enabled,
                    filter_skipped=True,
                    role="admin" if is_admin else "ventas",
                    reason=local_reason,
                    confidence=0.8
                )
    
    # 2. Build system prompt with user context
    system_prompt = build_system_prompt({
        "name": request.user.name,
        "id": request.user.id,
        "roles": user_roles,
        "authenticated": request.user.authenticated
    })
    
    # 3. Prepare messages for LLM
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.text}
    ]
    
    # 4. Call LLM
    try:
        llm_response = await llm_client.generate(messages)
        
        # Handle tool calls if present (simplified for now)
        # In a full implementation, we'd process tool calls here
        
        reply = llm_response.text
        
    except Exception as e:
        return ChatResponse(
            blocked=False,
            reply=f"Error al procesar tu solicitud: {str(e)}",
            filter_enabled=filter_enabled,
            filter_skipped=filter_skipped,
            role="admin" if is_admin else "ventas"
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
                    blocked=False,
                    reply="No puedo mostrar información sensible o credenciales en la respuesta.",
                    guard="BLOCK",
                    filter_enabled=filter_enabled,
                    output_guard_enabled=output_guard_enabled,
                    filter_skipped=filter_skipped,
                    output_guard_skipped=False,
                    role="admin" if is_admin else "ventas"
                )
            
            if guard_result.get("action") == "REDACT" and guard_result.get("redacted_response"):
                reply = guard_result["redacted_response"]
                
        except Exception as e:
            print(f"Output guard error: {e}")
            output_guard_skipped = True
    
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
        role="admin" if is_admin else "ventas",
        model=llm_response.model,
        filter_layers=filter_result.layers if filter_result else None
    )


@router.post("/tools/execute", tags=["tools"])
async def execute_tool(
    tool_name: str,
    args: dict,
    user_roles: List[str]
):
    """Execute an MCP tool with role-based access control"""
    mcp_executor = get_mcp_executor()
    
    result = mcp_executor.execute(tool_name, args, user_roles)
    
    return result