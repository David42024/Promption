"""API-key authentication for the multi-tenant Promption Filter API.

Clients send ``X-Promption-API-Key``. ``X-API-Key`` and Bearer auth remain
available for backwards compatibility. The authenticated key, never request
payload data, determines the tenant and its filtering thresholds.

Production consumer keys are registered with
``PROMPTION_API_KEYS="tenant:key,other:key2"``. Administrative keys use the
separate ``PROMPTION_ADMIN_API_KEYS`` registry. The legacy ``PIF_API_KEYS``
name is accepted during migration. When an environment registry exists, the
public local-demo keys from ``config/tenants.yaml`` are not loaded.
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.utils.config import ROOT_DIR

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


def _read_tenants_file() -> dict:
    if not TENANTS_PATH.exists():
        return {}
    with open(TENANTS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_registry(
    raw: str,
    scopes: list[str] | None = None,
) -> dict[str, "TenantContext"]:
    tenants: dict[str, TenantContext] = {}
    for pair in raw.split(","):
        if ":" not in pair:
            continue
        tenant_id, api_key = pair.split(":", 1)
        tenant_id = tenant_id.strip()
        api_key = api_key.strip()
        if tenant_id and api_key:
            tenants[api_key] = TenantContext(
                tenant_id=tenant_id,
                scopes=list(scopes or ["filter", "output_guard"]),
            )
    return tenants


def load_tenants() -> dict[str, TenantContext]:
    """Load the tenant registry without exposing or inferring API keys."""
    tenants: dict[str, TenantContext] = {}
    legacy_registry = os.environ.get("PIF_API_KEYS", "").strip()
    registry = os.environ.get("PROMPTION_API_KEYS", "").strip()
    admin_registry = os.environ.get("PROMPTION_ADMIN_API_KEYS", "").strip()
    single_key = os.environ.get("PROMPTION_API_KEY", "").strip()
    single_tenant = os.environ.get("PROMPTION_TENANT_ID", "").strip()
    has_environment_registry = bool(
        legacy_registry or registry or admin_registry or (single_key and single_tenant)
    )

    if not has_environment_registry:
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
                )

    tenants.update(_parse_registry(legacy_registry))
    tenants.update(_parse_registry(registry))
    tenants.update(_parse_registry(admin_registry, scopes=["*"]))
    if single_key and single_tenant:
        tenants[single_key] = TenantContext(tenant_id=single_tenant)
    return tenants


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
