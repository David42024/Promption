"""Evidence-based outcomes; denials and operational failures are distinct."""

TECHNICAL_REASONS = frozenset({
    "scope_unavailable", "scope_timeout", "scope_truncated", "invalid_scope_response",
    "guard_unavailable", "filter_unavailable", "llm_unavailable", "llm_timeout",
    "llm_invalid_response", "gateway_timeout", "cancelled", "tool_no_progress",
    "output_guard_unavailable", "invalid_output_guard_response", "provider_unavailable",
    "filter_rate_limited", "connection_error", "rate_limited", "internal_error",
    "invalid_guard_response", "guard_request_failed", "conversation_not_checked",
})


def decision_outcome(data: dict, technical: str | None = None) -> str:
    """Classify only known contracts; unknown vetoes never imply detection."""
    if technical:
        return "TECHNICAL_FAILURE"
    if data.get("blocked") is False:
        return "ALLOWED"
    if data.get("blocked") is not True:
        return "UNKNOWN"
    category = str(data.get("block_type") or "").lower()
    reason = str(data.get("reason") or "").lower()
    scope = data.get("scope") or {}
    if reason in TECHNICAL_REASONS or scope.get("reason") in TECHNICAL_REASONS:
        return "TECHNICAL_FAILURE"
    if category in {"scope", "authorization", "policy", "conversation_limit"}:
        return "POLICY_DENIAL"
    if reason in {"tool_access_denied", "conversation_too_large"}:
        return "POLICY_DENIAL"
    if reason in {"conversation_injection", "injection", "prompt_injection"} or category == "attack":
        return "SECURITY_BLOCK"
    if category in {"output_guard", "model_guard"}:
        if reason in {"insufficient_scope", "unauthorized", "permission_denied"}:
            return "POLICY_DENIAL"
        return "SECURITY_BLOCK"
    return "UNKNOWN"
