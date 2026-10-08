"""Regression test for Defect 1: PolicyInfo compatibility with _allowed_confidential_reply."""
import sys
from pathlib import Path
import pytest

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

from app.models import PolicyInfo, MCPToolCall
from app.routes import _allowed_confidential_reply


def test_admin_authorized_confidential_reply_does_not_raise():
    """Confidential response authorized for admin with tool in tool_names returns True without raising."""
    policy = PolicyInfo(
        allowed=True,
        matched=True,
        policy_id="confidential.data",
        resource="employees",
        tier="confidencial",
        tool_names=["getEmployees"],
        required_roles=["admin"],
        confidence=0.9,
        reason="authorized",
    )
    audit = [MCPToolCall(tool="getEmployees", allowed=True, tier="confidencial")]
    # Must succeed and return True
    assert _allowed_confidential_reply(roles=["admin"], audit=audit, policy=policy) is True


def test_confidential_reply_blocked_for_customer_and_guest():
    """Same confidential response is blocked for customer and guest roles."""
    policy = PolicyInfo(
        allowed=True,
        matched=True,
        policy_id="confidential.data",
        resource="employees",
        tier="confidencial",
        tool_names=["getEmployees"],
        required_roles=["admin"],
        confidence=0.9,
        reason="authorized",
    )
    audit = [MCPToolCall(tool="getEmployees", allowed=True, tier="confidencial")]
    assert _allowed_confidential_reply(roles=["customer"], audit=audit, policy=policy) is False
    assert _allowed_confidential_reply(roles=["guest"], audit=audit, policy=policy) is False
    assert _allowed_confidential_reply(roles=["ventas"], audit=audit, policy=policy) is False


def test_empty_tool_names_and_multiple_tools():
    """Empty tool_names does not authorize; multiple tools only authorize if matching executed tool."""
    # Empty tool_names: must NOT authorize confidential data
    policy_empty = PolicyInfo(
        allowed=True,
        matched=True,
        policy_id="confidential.data",
        resource="generic",
        tier="confidencial",
        tool_names=[],
        required_roles=["admin"],
        confidence=0.9,
        reason="authorized",
    )
    audit = [MCPToolCall(tool="getEmployees", allowed=True, tier="confidencial")]
    assert _allowed_confidential_reply(roles=["admin"], audit=audit, policy=policy_empty) is False

    # Multiple tools: authorizes if one of the authorized tools was executed
    policy_multi = PolicyInfo(
        allowed=True,
        matched=True,
        policy_id="confidential.multi",
        resource="reports",
        tier="confidencial",
        tool_names=["getRevenueReport", "getVIPClients"],
        required_roles=["admin"],
        confidence=0.9,
        reason="authorized",
    )
    audit_matching = [MCPToolCall(tool="getVIPClients", allowed=True, tier="confidencial")]
    assert _allowed_confidential_reply(roles=["admin"], audit=audit_matching, policy=policy_multi) is True

    audit_unrelated = [MCPToolCall(tool="otherTool", allowed=True, tier="confidencial")]
    assert _allowed_confidential_reply(roles=["admin"], audit=audit_unrelated, policy=policy_multi) is False


def test_missing_or_disallowed_policy_grants_no_permission():
    """None policy or policy.allowed=False never grants confidential permission."""
    audit = [MCPToolCall(tool="getEmployees", allowed=True, tier="confidencial")]
    assert _allowed_confidential_reply(roles=["admin"], audit=audit, policy=None) is False

    disallowed_policy = PolicyInfo(
        allowed=False,
        matched=True,
        policy_id="confidential.denied",
        resource="employees",
        tier="confidencial",
        tool_names=["getEmployees"],
        required_roles=["admin"],
        confidence=0.9,
        reason="denied",
    )
    assert _allowed_confidential_reply(roles=["admin"], audit=audit, policy=disallowed_policy) is False

    # Credentials policy never authorizes confidential reply
    cred_policy = PolicyInfo(
        allowed=True,
        matched=True,
        policy_id="confidential.credentials",
        resource="passwords",
        tier="confidencial",
        tool_names=["getCredentials"],
        required_roles=["admin"],
        confidence=0.9,
        reason="creds",
    )
    audit_cred = [MCPToolCall(tool="getCredentials", allowed=True, tier="confidencial")]
    assert _allowed_confidential_reply(roles=["admin"], audit=audit, policy=cred_policy) is False
