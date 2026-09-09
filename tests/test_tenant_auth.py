"""Contrato multi-tenant: auth por API key y umbrales por tenant."""
import asyncio

import pytest
from fastapi import HTTPException

from src.api.auth import TenantContext, authenticate, load_tenants, require_tenant
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
    t = asyncio.run(require_tenant(x_api_key=None, authorization="Bearer pif_demo_shop_123456"))
    assert t.tenant_id == "demo-shop"


def test_env_override(monkeypatch):
    monkeypatch.setenv("PIF_API_KEYS", "t1:key-abc")
    assert authenticate("key-abc").tenant_id == "t1"


def test_default_tenant_uses_global_filter():
    assert _filter_for(TenantContext(tenant_id="x")) is _filter


def test_tenant_thresholds_applied():
    flt = _filter_for(TenantContext(tenant_id="y", thresholds={"final": 0.4, "ml": 0.4}))
    assert flt.final_threshold == 0.4
    assert flt.ml.threshold == 0.4


def test_tenants_file_loads():
    assert "pif_demo_shop_123456" in load_tenants()
