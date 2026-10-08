"""API-key authentication for the multi-tenant Promption Filter API.

Clients send ``X-Promption-API-Key``. ``X-API-Key`` and Bearer auth remain
available for backwards compatibility. The authenticated key, never request
payload data, determines the tenant and its filtering thresholds.

Production consumer keys are registered with
``PROMPTION_API_KEYS="tenant:key,other:key2"``. Administrative keys use the
separate ``PROMPTION_ADMIN_API_KEYS`` registry. The legacy ``PIF_API_KEYS``
name is accepted during migration.

DEMO MODE:
Public local-demo keys from ``config/tenants.yaml`` are ONLY loaded if
``PROMPTION_DEMO_MODE=true`` (or 1, yes) is explicitly enabled.
Demo mode is disabled by default. In production environments (indicated by
``ENVIRONMENT=production``, ``PROMPTION_ENV=production``, etc.), demo mode is
strictly forbidden and rejected.
When an environment registry exists, public demo keys are never loaded,
preserving credential precedence.
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from promption.utils.config import ROOT_DIR

TENANTS_PATH = Path(ROOT_DIR) / "config" / "tenants.yaml"
PROMPTION_API_KEY_HEADER = "X-Promption-API-Key"
_promption_api_key = APIKeyHeader(
    name=PROMPTION_API_KEY_HEADER,
    scheme_name="PromptionApiKey",
    description="Server-side API key issued to your business",
    auto_error=False,
)


@dataclass
class TenantContext:
    tenant_id: str
    name: str = ""
    thresholds: dict = field(default_factory=dict)
    roles: list = field(default_factory=list)
    scopes: list[str] = field(default_factory=lambda: ["filter", "output_guard"])
    quotas: dict = field(default_factory=dict)


def is_production_environment() -> bool:
    """Return True if any standard environment variable declares a production environment."""
    for var in ("PROMPTION_ENV", "ENVIRONMENT", "ENV", "NODE_ENV"):
        val = os.environ.get(var, "").strip().lower()
        if val in ("production", "prod"):
            return True
    return False


def is_demo_mode() -> bool:
    """Return True if demo mode is explicitly enabled.

    Demo mode is disabled by default. In declared production environments,
    activating demo mode raises a RuntimeError to prevent running with public keys.
    """
    raw = os.environ.get("PROMPTION_DEMO_MODE", "").strip().lower()
    enabled = raw in ("true", "1", "yes", "t", "on")
    if enabled and is_production_environment():
        raise RuntimeError("PROMPTION_DEMO_MODE cannot be enabled in a production environment.")
    return enabled


def _read_tenants_file() -> dict:
    if not TENANTS_PATH.exists():
        return {}
    with open(TENANTS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_registry(
    raw: str,
    scopes: list[str] | None = None,
) -> dict[str, TenantContext]:
    tenants: dict[str, TenantContext] = {}
    if not raw or not raw.strip():
        return tenants
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise ValueError("Malformed API key registry: entries must follow 'tenant_id:key' format")
        tenant_id, api_key = pair.split(":", 1)
        tenant_id = tenant_id.strip()
        api_key = api_key.strip()
        if not tenant_id or not api_key:
            raise ValueError("Malformed API key registry: tenant_id and key must not be empty")
        tenants[api_key] = TenantContext(
            tenant_id=tenant_id,
            scopes=list(scopes or ["filter", "output_guard"]),
        )
    return tenants


def load_tenants(allow_demo: bool | None = None) -> dict[str, TenantContext]:
    """Load the tenant registry without exposing or inferring API keys.

    Public demo keys from config/tenants.yaml are ONLY loaded if allow_demo=True
    or PROMPTION_DEMO_MODE=true, and no environment credentials are configured.
    Demo mode is strictly rejected in production environments.
    """
    demo_active = is_demo_mode() if allow_demo is None else bool(allow_demo)
    if demo_active and is_production_environment():
        raise RuntimeError("PROMPTION_DEMO_MODE cannot be enabled in a production environment.")

    tenants: dict[str, TenantContext] = {}
    legacy_registry = os.environ.get("PIF_API_KEYS", "").strip()
    registry = os.environ.get("PROMPTION_API_KEYS", "").strip()
    admin_registry = os.environ.get("PROMPTION_ADMIN_API_KEYS", "").strip()
    single_key = os.environ.get("PROMPTION_API_KEY", "").strip()
    single_tenant = os.environ.get("PROMPTION_TENANT_ID", "").strip()

    if (single_key and not single_tenant) or (single_tenant and not single_key):
        raise ValueError("Incomplete single-tenant configuration: both PROMPTION_API_KEY and PROMPTION_TENANT_ID must be set")

    has_environment_registry = bool(
        legacy_registry or registry or admin_registry or (single_key and single_tenant)
    )

    if not has_environment_registry and demo_active and not is_production_environment():
        for entry in _read_tenants_file().get("tenants", []) or []:
            tenant_id = str(entry.get("tenant_id", "")).strip()
            api_key = str(entry.get("api_key", "")).strip()
            if tenant_id and api_key:
                tenants[api_key] = TenantContext(
                    tenant_id=tenant_id,
                    name=str(entry.get("name", "")),
                    thresholds=dict(entry.get("thresholds", {}) or {}),
                    roles=list(entry.get("roles", []) or []),
                    scopes=list(entry.get("scopes", ["filter", "output_guard"]) or []),
                    quotas=dict(entry.get("quotas", {}) or {}),
                )

    tenants.update(_parse_registry(legacy_registry))
    tenants.update(_parse_registry(registry))
    tenants.update(_parse_registry(admin_registry, scopes=["*"]))
    if single_key and single_tenant:
        tenants[single_key] = TenantContext(tenant_id=single_tenant)
    return tenants


def validate_auth_configuration() -> None:
    """Validate that authentication is properly configured at API startup.

    Raises RuntimeError or ValueError if:
    - Demo mode is attempted in production.
    - Environment registry is malformed or incomplete (even in demo mode).
    - Outside of demo mode, no valid credentials exist.
    """
    if is_demo_mode() and is_production_environment():
        raise RuntimeError("PROMPTION_DEMO_MODE cannot be enabled in a production environment.")

    # Always call load_tenants() to validate all environment registries, single-tenant vars,
    # and demo keys against malformed or incomplete configurations.
    tenants = load_tenants()

    if not is_demo_mode() and not tenants:
        raise RuntimeError(
            "Authentication credentials missing. In non-demo environments, valid API keys "
            "must be configured via PROMPTION_API_KEYS or PROMPTION_API_KEY. "
            "To enable local demo keys, set PROMPTION_DEMO_MODE=true (forbidden in production)."
        )


def authenticate(api_key: str | None) -> TenantContext:
    """Valida la key con comparación constante; 401 si falta o es inválida."""
    if api_key:
        for key, tenant in load_tenants().items():
            if hmac.compare_digest(api_key, key):
                return tenant
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Falta {PROMPTION_API_KEY_HEADER} válida",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_tenant(
    promption_api_key: str | None = Security(_promption_api_key),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> TenantContext:
    """Dependencia FastAPI: inyecta el TenantContext autenticado."""
    key = (promption_api_key or x_api_key or "").strip()
    if not key and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            key = token.strip()
    return authenticate(key or None)


def require_scope(scope: str):
    """Build a FastAPI dependency that restricts a key to one API capability."""
    async def dependency(tenant: TenantContext = Depends(require_tenant)) -> TenantContext:
        if scope not in tenant.scopes and "*" not in tenant.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"La API key no tiene el scope '{scope}'",
            )
        return tenant

    return dependency
