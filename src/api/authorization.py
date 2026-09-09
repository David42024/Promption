"""Authorization layer: endpoint allowlist by role for tool-calling protection."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.utils.logger import logger


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
]


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

    endpoint_normalized = endpoint.lower().strip()
    
    for pattern, severity, pattern_path in _SENSITIVE_PATTERNS:
        pattern_path_normalized = pattern_path.lower()
        if pattern_path_normalized in endpoint_normalized:
            logger.warning(
                "Auth blocked: sensitive endpoint pattern=%s requested=%s roles=%s severity=%s",
                pattern, endpoint, roles, severity,
            )
            log_authorization_attempt(endpoint, roles, False, f"Endpoint sensible bloqueado: {pattern}", 
                                      category="credentials", severity=severity, tenant_id=tenant_id, user_id=user_id)
            return False, f"Endpoint sensible bloqueado: {pattern}", None

    for role in roles:
        role_rules = _ROLE_ENDPOINTS.get(role, [])
        for rule in role_rules:
            if rule.path.lower() in endpoint_normalized:
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
        from src.utils.structured_logger import log_authorization
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
