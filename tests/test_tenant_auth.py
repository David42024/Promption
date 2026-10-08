"""Contrato multi-tenant: auth por API key, modo demo explícito y umbrales por tenant."""
import asyncio
import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from promption.api.auth import (
    TenantContext,
    authenticate,
    is_demo_mode,
    is_production_environment,
    load_tenants,
    require_scope,
    require_tenant,
    validate_auth_configuration,
)
from promption.api.main import app
from promption.api.routes import _filter, _filter_for


# ----------------------------------------------------------------------
# 1. Modo demo explícito y rechazo por defecto
# ----------------------------------------------------------------------
def test_demo_keys_rejected_by_default_without_demo_mode(monkeypatch):
    monkeypatch.delenv("PROMPTION_DEMO_MODE", raising=False)
    monkeypatch.delenv("PROMPTION_API_KEYS", raising=False)
    monkeypatch.delenv("PIF_API_KEYS", raising=False)
    monkeypatch.delenv("PROMPTION_ADMIN_API_KEYS", raising=False)
    monkeypatch.delenv("PROMPTION_API_KEY", raising=False)
    monkeypatch.delenv("PROMPTION_TENANT_ID", raising=False)

    # By default, demo keys must NOT be loaded
    assert load_tenants() == {}
    with pytest.raises(HTTPException) as exc:
        authenticate("pif_demo_shop_123456")
    assert exc.value.status_code == 401


def test_demo_tenant_resolves_when_demo_mode_explicit(monkeypatch):
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    monkeypatch.delenv("PROMPTION_API_KEYS", raising=False)
    monkeypatch.delenv("PIF_API_KEYS", raising=False)

    t = authenticate("pif_demo_shop_123456")
    assert t.tenant_id == "demo-shop"


def test_tenants_file_loads_with_explicit_demo(monkeypatch):
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    monkeypatch.delenv("PROMPTION_API_KEYS", raising=False)

    tenants = load_tenants()
    assert "pif_demo_shop_123456" in tenants
    assert tenants["pk-123-tenant123.unitru"].tenant_id == "tenant123.unitru"


def test_tenants_file_empty_without_explicit_demo(monkeypatch):
    monkeypatch.delenv("PROMPTION_DEMO_MODE", raising=False)
    monkeypatch.delenv("PROMPTION_API_KEYS", raising=False)
    monkeypatch.delenv("PIF_API_KEYS", raising=False)

    assert load_tenants() == {}


# ----------------------------------------------------------------------
# 2. Rechazo de solicitudes protegidas sin credenciales ni modo demo
# ----------------------------------------------------------------------
def test_protected_requests_rejected_without_credentials_and_without_demo(monkeypatch):
    monkeypatch.delenv("PROMPTION_DEMO_MODE", raising=False)
    monkeypatch.delenv("PROMPTION_API_KEYS", raising=False)
    monkeypatch.delenv("PIF_API_KEYS", raising=False)

    client = TestClient(app)
    # Using public key without demo mode must be rejected (401)
    res = client.post(
        "/api/v1/filter",
        json={"text": "Hello world", "use_ml": False},
        headers={"Authorization": "Bearer pif_demo_shop_123456"},
    )
    assert res.status_code == 401
    assert "falta x-promption-api-key válida" in res.text.lower()


def test_unknown_key_rejected(monkeypatch):
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    with pytest.raises(HTTPException) as exc:
        authenticate("nope")
    assert exc.value.status_code == 401


def test_missing_key_rejected():
    with pytest.raises(HTTPException) as exc:
        authenticate(None)
    assert exc.value.status_code == 401


# ----------------------------------------------------------------------
# 3. Rechazo de modo demo en producción
# ----------------------------------------------------------------------
@pytest.mark.parametrize("env_var", ["ENVIRONMENT", "PROMPTION_ENV", "ENV", "NODE_ENV"])
def test_demo_mode_rejected_in_production(monkeypatch, env_var):
    monkeypatch.setenv(env_var, "production")
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")

    assert is_production_environment() is True
    with pytest.raises(RuntimeError) as exc_info:
        is_demo_mode()
    assert "production" in str(exc_info.value).lower()

    with pytest.raises(RuntimeError):
        load_tenants()

    with pytest.raises(RuntimeError):
        validate_auth_configuration()


# ----------------------------------------------------------------------
# 4. Validación de configuración y registro al arrancar
# ----------------------------------------------------------------------
def test_validate_auth_fails_without_credentials_or_demo(monkeypatch):
    monkeypatch.delenv("PROMPTION_DEMO_MODE", raising=False)
    monkeypatch.delenv("PROMPTION_API_KEYS", raising=False)
    monkeypatch.delenv("PIF_API_KEYS", raising=False)
    monkeypatch.delenv("PROMPTION_ADMIN_API_KEYS", raising=False)
    monkeypatch.delenv("PROMPTION_API_KEY", raising=False)
    monkeypatch.delenv("PROMPTION_TENANT_ID", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        validate_auth_configuration()
    assert "credentials missing" in str(exc_info.value).lower()


def test_validate_auth_fails_with_malformed_registry_and_does_not_reveal_secrets(monkeypatch):
    secret_key = "super_confidential_token_value_xyz"
    monkeypatch.setenv("PROMPTION_API_KEYS", f"invalid_format_without_colon,{secret_key}")

    with pytest.raises(ValueError) as exc_info:
        validate_auth_configuration()
    # Must NOT reveal the raw secret key in error message
    assert secret_key not in str(exc_info.value)
    assert "malformed" in str(exc_info.value).lower()


def test_malformed_registry_rejected_even_in_demo_mode(monkeypatch):
    secret_key = "super_confidential_token_value_xyz"
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    monkeypatch.setenv("PROMPTION_API_KEYS", f"invalid_format_without_colon,{secret_key}")

    with pytest.raises(ValueError) as exc_info:
        validate_auth_configuration()
    assert secret_key not in str(exc_info.value)
    assert "malformed" in str(exc_info.value).lower()


def test_startup_validation_rejects_malformed_registry_in_demo_mode(monkeypatch):
    secret_key = "secret_in_demo_registry"
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    monkeypatch.setenv("PROMPTION_API_KEYS", f"entry_without_colon,{secret_key}")

    from promption.api.main import _startup_auth_validation
    with pytest.raises(ValueError) as exc_info:
        _startup_auth_validation()
    assert secret_key not in str(exc_info.value)
    assert "malformed" in str(exc_info.value).lower()


def test_validate_auth_fails_with_incomplete_single_tenant(monkeypatch):
    secret_key = "single_confidential_key_123"
    monkeypatch.setenv("PROMPTION_API_KEY", secret_key)
    monkeypatch.delenv("PROMPTION_TENANT_ID", raising=False)

    with pytest.raises(ValueError) as exc_info:
        validate_auth_configuration()
    assert secret_key not in str(exc_info.value)
    assert "incomplete" in str(exc_info.value).lower()


def test_validate_auth_succeeds_in_production_with_valid_registry(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PROMPTION_API_KEYS", "corp-tenant:corp-secret-token")
    monkeypatch.delenv("PROMPTION_DEMO_MODE", raising=False)

    # Must succeed without error
    validate_auth_configuration()
    assert authenticate("corp-secret-token").tenant_id == "corp-tenant"


def test_validate_auth_succeeds_with_demo_mode(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("PROMPTION_ENV", raising=False)
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")

    # Must succeed in non-production demo mode
    validate_auth_configuration()


# ----------------------------------------------------------------------
# 5. Encabezados, registros de entorno y scopes
# ----------------------------------------------------------------------
def test_bearer_header_accepted(monkeypatch):
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    t = asyncio.run(require_tenant(
        promption_api_key=None,
        x_api_key=None,
        authorization="Bearer pif_demo_shop_123456",
    ))
    assert t.tenant_id == "demo-shop"


def test_canonical_header_accepted(monkeypatch):
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    t = asyncio.run(require_tenant(
        promption_api_key="pk-123-tenant123.unitru",
        x_api_key=None,
        authorization=None,
    ))
    assert t.tenant_id == "tenant123.unitru"


def test_consumer_key_scopes_are_limited(monkeypatch):
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    tenant = authenticate("pk-123-tenant123.unitru")
    assert tenant.scopes == ["filter", "output_guard"]


def test_missing_scope_is_rejected():
    dependency = require_scope("admin")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(TenantContext(tenant_id="business-a")))
    assert exc.value.status_code == 403


def test_legacy_env_registry(monkeypatch):
    monkeypatch.setenv("PIF_API_KEYS", "t1:key-abc")
    assert authenticate("key-abc").tenant_id == "t1"


def test_promption_env_registry_replaces_public_demo_keys(monkeypatch):
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
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


def test_default_tenant_uses_global_filter():
    assert _filter_for(TenantContext(tenant_id="x")) is _filter


def test_tenant_thresholds_applied():
    flt = _filter_for(TenantContext(tenant_id="y", thresholds={"heuristic": 0.4, "ml": 0.4}))
    assert flt.heuristic.threshold == 0.4
    assert flt.high_threshold == 0.4


def test_reject_threshold(monkeypatch):
    monkeypatch.setenv("PROMPTION_DEMO_MODE", "true")
    client = TestClient(app)
    # With threshold = 0.5
    res = client.post(
        "/api/v1/filter",
        json={"text": "hello", "threshold": 0.5},
        headers={"Authorization": "Bearer pif_demo_shop_123456"},
    )
    assert res.status_code == 422
    assert "threshold" in res.text.lower()
    # With threshold = None
    res = client.post(
        "/api/v1/filter",
        json={"text": "hello", "threshold": None},
        headers={"Authorization": "Bearer pif_demo_shop_123456"},
    )
    assert res.status_code == 422
    assert "threshold" in res.text.lower()
