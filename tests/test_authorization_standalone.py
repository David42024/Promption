"""Standalone authorization tests without conftest dependencies."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.authorization import (
    Severity,
    check_endpoint_authorization,
    log_authorization_attempt,
)


def test_public_endpoint_allowed_for_all_roles():
    allowed, reason, rule = check_endpoint_authorization("/api/v1/products", ["ventas"])
    assert allowed is True
    assert reason is None
    assert rule is not None
    assert rule.category == "catalog"
    print("[PASS] test_public_endpoint_allowed_for_all_roles")


def test_admin_only_endpoint_denied_for_ventas():
    allowed, reason, rule = check_endpoint_authorization("/api/v1/users", ["ventas"])
    assert allowed is False
    assert "no autorizado" in reason.lower()
    assert rule is None
    print("[PASS] test_admin_only_endpoint_denied_for_ventas")


def test_sensitive_credentials_pattern_blocked():
    sensitive_endpoints = [
        "/api/v1/users/credentials",
        "/api/v1/users/apikey",
        "/api/v1/users/password",
        "/api/v1/users/token",
        "/api/v1/users/jwt",
        "/internal/keys",
        "/internal/secrets",
        "/api/v1/credentials",
        "/api/v1/secrets",
        "/api/v1/keys",
    ]
    for endpoint in sensitive_endpoints:
        allowed, reason, rule = check_endpoint_authorization(endpoint, ["admin"])
        assert allowed is False, f"Endpoint {endpoint} should be blocked even for admin"
        assert "sensible" in reason.lower()
        assert rule is None
    print("[PASS] test_sensitive_credentials_pattern_blocked")


def test_no_roles_denied():
    allowed, reason, rule = check_endpoint_authorization("/api/v1/products", [])
    assert allowed is False
    assert "sin roles" in reason.lower()
    print("[PASS] test_no_roles_denied")


def test_non_strict_mode_allows_unknown_endpoints():
    allowed, reason, rule = check_endpoint_authorization("/api/v1/unknown", ["ventas"], strict=False)
    assert allowed is True
    assert reason is None
    print("[PASS] test_non_strict_mode_allows_unknown_endpoints")


def test_strict_mode_blocks_unknown_endpoints():
    allowed, reason, rule = check_endpoint_authorization("/api/v1/unknown", ["ventas"], strict=True)
    assert allowed is False
    assert "no autorizado" in reason.lower()
    print("[PASS] test_strict_mode_blocks_unknown_endpoints")


if __name__ == "__main__":
    test_public_endpoint_allowed_for_all_roles()
    test_admin_only_endpoint_denied_for_ventas()
    test_sensitive_credentials_pattern_blocked()
    test_no_roles_denied()
    test_non_strict_mode_allows_unknown_endpoints()
    test_strict_mode_blocks_unknown_endpoints()
    print("\n[SUCCESS] All authorization tests passed!")
