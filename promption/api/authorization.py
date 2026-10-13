"""Authorization layer: endpoint allowlist by role for tool-calling protection."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import unquote, urlsplit

from promption.utils.logger import logger


class Severity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class EndpointRule:
    path: str
    allowed_roles: list[str]
    category: str
    severity: Severity
    description: str


_ROLE_ENDPOINTS: dict[str, list[EndpointRule]] = {
    "ventas": [
        EndpointRule(
            path="/api/v1/products",
            allowed_roles=["ventas", "admin"],
            category="catalog",
            severity=Severity.LOW,
            description="Catálogo de productos",
        ),
        EndpointRule(
            path="/api/v1/orders",
            allowed_roles=["ventas", "admin"],
            category="orders",
            severity=Severity.MEDIUM,
            description="Gestión de pedidos",
        ),
        EndpointRule(
            path="/api/v1/discounts",
            allowed_roles=["ventas", "admin"],
            category="catalog",
            severity=Severity.LOW,
            description="Descuentos públicos",
        ),
    ],
    "admin": [
        EndpointRule(
            path="/api/v1/users",
            allowed_roles=["admin"],
            category="users",
            severity=Severity.HIGH,
            description="Gestión de usuarios",
        ),
        EndpointRule(
            path="/api/v1/config",
            allowed_roles=["admin"],
            category="config",
            severity=Severity.HIGH,
            description="Configuración del sistema",
        ),
        EndpointRule(
            path="/api/v1/analytics",
            allowed_roles=["admin"],
            category="analytics",
            severity=Severity.MEDIUM,
            description="Métricas y analytics",
        ),
    ],
}

_SENSITIVE_PATTERNS = [
    ("credentials", Severity.CRITICAL, "/credentials"),
    ("credentials", Severity.CRITICAL, "/apikey"),
    ("credentials", Severity.CRITICAL, "/password"),
    ("credentials", Severity.CRITICAL, "/token"),
    ("credentials", Severity.CRITICAL, "/jwt"),
    ("credentials", Severity.CRITICAL, "/keys"),
    ("credentials", Severity.CRITICAL, "/secrets"),
    ("configuration", Severity.CRITICAL, "/internal/config"),
]


def _normalized_endpoint_path(endpoint: str) -> str | None:
    """Accept local absolute API paths, not URL strings or encoded path tricks."""
    if not isinstance(endpoint, str) or not endpoint.startswith("/") or endpoint.startswith("//"):
        return None
    if any(ord(char) < 32 or char == "\\" for char in endpoint):
        return None
    parsed = urlsplit(endpoint)
    if parsed.scheme or parsed.netloc:
        return None
    original_path = parsed.path
    # Reject encoded separators and traversal rather than relying on framework normalization.
    if any(code in original_path.lower() for code in ("%2f", "%5c", "%00", "%25")):
        return None
    decoded = unquote(original_path)
    if decoded != original_path and ("/" in decoded[len(original_path):] or "\\" in decoded):
        return None
    path_segments = decoded.split("/")
    if any(part in (".", "..") or not part for part in path_segments[1:-1]):
        return None
    if "%" in decoded or "\\" in decoded:
        return None
    normalized = "/" + "/".join(s.lower() for s in path_segments if s)
    return normalized.rstrip("/") or "/"


def _path_in_route(path: str, route: str) -> bool:
    route = route.lower().rstrip("/")
    return path == route or path.startswith(route + "/")


def check_endpoint_authorization(
    endpoint: str,
    roles: list[str],
    strict: bool = True,
    tenant_id: str = "system",
    user_id: str | None = None,
) -> tuple[bool, str | None, EndpointRule | None]:
    """
    Verifica si un endpoint está permitido para los roles dados.
    
    Returns:
        (allowed, reason, rule)
    """
    if not roles:
        log_authorization_attempt(endpoint, roles, False, "Sin roles autenticados", tenant_id=tenant_id, user_id=user_id)
        return False, "Sin roles autenticados", None

    endpoint_normalized = _normalized_endpoint_path(endpoint)
    if endpoint_normalized is None:
        log_authorization_attempt(endpoint, roles, False, "Ruta inválida", tenant_id=tenant_id, user_id=user_id)
        return False, "Ruta inválida", None

    segments = endpoint_normalized.split("/")[1:]
    for pattern, severity, pattern_path in _SENSITIVE_PATTERNS:
        restricted = pattern_path.strip("/").split("/")
        # Full contiguous segments; /tokenization and /apitoken are not credentials.
        if any(segments[i:i+len(restricted)] == restricted
               for i in range(len(segments)-len(restricted)+1)):
            logger.warning(
                "Auth blocked: sensitive endpoint pattern=%s requested=%s roles=%s severity=%s",
                pattern, endpoint, roles, severity,
            )
            log_authorization_attempt(endpoint, roles, False, f"Endpoint sensible bloqueado: {pattern}", 
                                      category="credentials", severity=severity, tenant_id=tenant_id, user_id=user_id)
            return False, f"Endpoint sensible bloqueado: {pattern}", None

    for rule_group in _ROLE_ENDPOINTS.values():
        for rule in rule_group:
            if any(str(role).lower() in rule.allowed_roles for role in roles) and _path_in_route(endpoint_normalized, rule.path):
                logger.info(
                    "Auth allowed: endpoint=%s roles=%s category=%s",
                    endpoint, roles, rule.category,
                )
                log_authorization_attempt(endpoint, roles, True, category=rule.category, 
                                        severity=rule.severity, tenant_id=tenant_id, user_id=user_id)
                return True, None, rule

    if strict:
        logger.warning(
            "Auth denied: endpoint=%s not in allowlist roles=%s",
            endpoint, roles,
        )
        log_authorization_attempt(endpoint, roles, False, "Endpoint no autorizado para estos roles",
                                  tenant_id=tenant_id, user_id=user_id)
        return False, "Endpoint no autorizado para estos roles", None

    logger.info(
        "Auth non-strict: endpoint=%s allowed by default roles=%s",
        endpoint, roles,
    )
    log_authorization_attempt(endpoint, roles, True, tenant_id=tenant_id, user_id=user_id)
    return True, None, None


def log_authorization_attempt(
    endpoint: str,
    roles: list[str],
    allowed: bool,
    reason: str | None = None,
    category: str | None = None,
    severity: Severity | None = None,
    tenant_id: str = "system",
    user_id: str | None = None,
) -> None:
    """Log seguro de intentos de autorización (sin valores sensibles)."""
    if allowed:
        logger.info(
            "Auth success: endpoint=%s roles=%s category=%s",
            endpoint, roles, category or "unknown",
        )
    else:
        logger.warning(
            "Auth blocked: endpoint=%s roles=%s reason=%s category=%s severity=%s",
            endpoint, roles, reason or "unknown", category or "unknown", severity or "unknown",
        )
    
    # Structured logging
    try:
        from promption.utils.structured_logger import log_authorization
        log_authorization(
            allowed=allowed,
            endpoint=endpoint,
            roles=roles,
            tenant_id=tenant_id,
            user_id=user_id,
            reason=reason,
        )
    except Exception:
        pass  # Don't fail if structured logging fails
