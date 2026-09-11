"""Autenticación por tenant (API keys) para el Filter API multi-negocio.

Contrato:
    X-API-Key: <key>  (o Authorization: Bearer <key>)

La identidad del tenant sale de la key; cada request queda auditada
con su ``tenant_id`` y aplica sus umbrales propios. Las keys demo viven
en ``config/tenants.yaml``; en producción se inyectan con la variable
``PIF_API_KEYS="tenant:key,otro:key2"`` (prevalece, no se commitea).
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from fastapi import Header, HTTPException, status

from src.utils.config import ROOT_DIR

TENANTS_PATH = Path(ROOT_DIR) / "config" / "tenants.yaml"


@dataclass
class TenantContext:
    tenant_id: str
    name: str = ""
    thresholds: dict = field(default_factory=dict)
    roles: list = field(default_factory=list)


def _read_tenants_file() -> dict:
    if not TENANTS_PATH.exists():
        return {}
    with open(TENANTS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_tenants() -> dict[str, TenantContext]:
    """Fusiona tenants.yaml con PIF_API_KEYS (env gana)."""
    tenants: dict[str, TenantContext] = {}
    for entry in _read_tenants_file().get("tenants", []) or []:
        tid = str(entry.get("tenant_id", "")).strip()
        key = str(entry.get("api_key", "")).strip()
        if tid and key:
            tenants[key] = TenantContext(
                tenant_id=tid,
                name=str(entry.get("name", "")),
                thresholds=dict(entry.get("thresholds", {}) or {}),
                roles=list(entry.get("roles", ["cliente"] or [])),
            )
    for pair in os.environ.get("PIF_API_KEYS", "").split(","):
        if ":" not in pair:
            continue
        tid, key = pair.split(":", 1)
        if tid.strip() and key.strip():
            tenants[key.strip()] = TenantContext(tenant_id=tid.strip())
    return tenants


def authenticate(api_key: str | None) -> TenantContext:
    """Valida la key con comparación constante; 401 si falta o es inválida."""
    if api_key:
        for key, tenant in load_tenants().items():
            if hmac.compare_digest(api_key, key):
                return tenant
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Falta X-API-Key válida (o Authorization: Bearer <key>)",
    )


async def require_tenant(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> TenantContext:
    """Dependencia FastAPI: inyecta el TenantContext autenticado."""
    key = (x_api_key or "").strip()
    if not key and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            key = token.strip()
    return authenticate(key or None)
