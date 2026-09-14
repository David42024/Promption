"""Contrato multi-tenant: auth por API key y umbrales por tenant."""
import asyncio

import pytest
from fastapi import HTTPException

from src.api.auth import TenantContext, authenticate, load_tenants, require_scope, require_tenant
from src.api.routes import _filter, _filter_for


def test_demo_tenant_resolves():
    t = authenticate("pif_demo_shop_123456")
    assert t.tenant_id == "demo-shop"


def test_unknown_key_rejected():
    with pytest.raises(HTTPException) as exc:
        authenticate("nope")
    assert exc.value.status_code == 401


def test_missing_key_rejected():
    with pytest.raises(HTTPException) as exc:
        authenticate(None)
    assert exc.value.status_code == 401


def test_bearer_header_accepted():
    t = asyncio.run(require_tenant(
        promption_api_key=None,
        x_api_key=None,
        authorization="Bearer pif_demo_shop_123456",
    ))
    assert t.tenant_id == "demo-shop"


def test_legacy_env_registry(monkeypatch):
    monkeypatch.setenv("PIF_API_KEYS", "t1:key-abc")
    assert authenticate("key-abc").tenant_id == "t1"


def test_promption_env_registry_replaces_public_demo_keys(monkeypatch):
    monkeypatch.setenv("PROMPTION_API_KEYS", "business-a:pk-live-long-random-value")
    assert authenticate("pk-live-long-random-value").tenant_id == "business-a"
    with pytest.raises(HTTPException):
        authenticate("pif_demo_shop_123456")


def test_single_tenant_environment(monkeypatch):
    monkeypatch.setenv("PROMPTION_API_KEY", "pk-live-single-business")
    monkeypatch.setenv("PROMPTION_TENANT_ID", "single-business")
    assert authenticate("pk-live-single-business").tenant_id == "single-business"


def test_admin_registry_grants_all_scopes(monkeypatch):
    monkeypatch.setenv("PROMPTION_ADMIN_API_KEYS", "platform:pk-admin-random-value")
    tenant = authenticate("pk-admin-random-value")
    assert tenant.tenant_id == "platform"
    assert tenant.scopes == ["*"]


def test_canonical_header_accepted():
    t = asyncio.run(require_tenant(
        promption_api_key="pk-123-tenant123.unitru",
        x_api_key=None,
        authorization=None,
    ))
    assert t.tenant_id == "tenant123.unitru"


def test_consumer_key_scopes_are_limited():
    tenant = authenticate("pk-123-tenant123.unitru")
    assert tenant.scopes == ["filter", "output_guard"]


def test_missing_scope_is_rejected():
    dependency = require_scope("admin")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(TenantContext(tenant_id="business-a")))
    assert exc.value.status_code == 403


def test_default_tenant_uses_global_filter():
    assert _filter_for(TenantContext(tenant_id="x")) is _filter


def test_tenant_thresholds_applied():
    flt = _filter_for(TenantContext(tenant_id="y", thresholds={"final": 0.4, "ml": 0.4}))
    assert flt.final_threshold == 0.4
    assert flt.ml_threshold == 0.4


def test_tenants_file_loads():
    assert "pif_demo_shop_123456" in load_tenants()
    assert load_tenants()["pk-123-tenant123.unitru"].tenant_id == "tenant123.unitru"
