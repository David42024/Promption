"""Local and asynchronous guard pipelines independent of web frameworks."""
from dataclasses import dataclass
from typing import Any, Callable, Literal


@dataclass(frozen=True)
class Identity:
    user_id: str
    roles: tuple[str, ...] = ()
    authenticated: bool = False


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    text: str
    action: str
    reason: str = ""
    status: int = 200
    requires_output_guard: bool = False
    conversation_checked: bool = False

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "text": self.text, "action": self.action,
                "reason": self.reason, "requires_output_guard": self.requires_output_guard,
                "conversation_checked": self.conversation_checked}


def _field(result: Any, key: str, default: Any = None) -> Any:
    return result.get(key, default) if isinstance(result, dict) else getattr(result, key, default)


class Promption:
    """Use the input filter, application ACL and Output Guard in process."""

    def __init__(self, *, input_filter=None, policy=None, admin_role: str = "admin"):
        from .filter.ensemble_filter import EnsembleFilter
        self.input_filter = input_filter if input_filter is not None else EnsembleFilter()
        self.policy = policy
        self.admin_role = admin_role

    def check_input(self, text: str, identity: Identity | None = None, *, use_ml: bool = True) -> GuardDecision:
        identity = identity or Identity("anonymous")
        if self.policy and not self.policy.evaluate(text, identity.roles).allowed:
            return GuardDecision(False, "", "BLOCK", "insufficient_scope", 403)
        result = self.input_filter.analyze(text, use_ml=use_ml, roles=list(identity.roles))
        return GuardDecision(not result.blocked, text if not result.blocked else "",
                             result.decision, result.blocking_reason,
                             403 if result.blocked else 200, result.requires_output_guard)

    def check_conversation(self, messages: list, identity: Identity | None = None,
                           *, use_ml: bool = True) -> GuardDecision:
        from .conversation_guard import ConversationGuard, ConversationLimitError
        identity = identity or Identity("anonymous")
        try:
            result = ConversationGuard(self.input_filter).analyze(messages, roles=list(identity.roles), use_ml=use_ml)
        except ConversationLimitError:
            return GuardDecision(False, "", "BLOCK", "conversation_limit", 413)
        return GuardDecision(not result.blocked, "", "BLOCK" if result.blocked else "PASS",
                             result.reason, 403 if result.blocked else 200, result.requires_output_guard)

    def check_output(self, text: str, identity: Identity | None = None) -> GuardDecision:
        from .output_guard import guard_response
        identity = identity or Identity("anonymous")
        if self.policy and not self.policy.evaluate_output(text, identity.roles).allowed:
            return GuardDecision(False, "", "BLOCK", "insufficient_scope", 403)
        result = guard_response(text, admin_mode=self.admin_role in identity.roles)
        return _output_decision(text, result)


def _output_decision(text: str, result: Any) -> GuardDecision:
    action = _field(result, "action")
    if action == "BLOCK":
        return GuardDecision(False, "", "BLOCK", "sensitive_output", 403)
    if action == "REDACT":
        redacted = _field(result, "redacted_response")
        if not isinstance(redacted, str):
            return GuardDecision(False, "", "BLOCK", "invalid_guard_response", 503)
        return GuardDecision(True, redacted, "REDACT")
    if action != "PASS":
        return GuardDecision(False, "", "BLOCK", "invalid_guard_response", 503)
    return GuardDecision(True, text, "PASS")


class AsyncGuardPipeline:
    """Compose remote/local checks and ACL, failing closed on guard service errors."""

    def __init__(self, *, filter_input: Callable, guard_output: Callable, policy=None):
        self.filter_input = filter_input
        self.guard_output = guard_output
        self.policy = policy

    async def check(self, text: str, direction: Literal["input", "output"], identity: Identity,
                    *, input_enabled: bool = True, output_enabled: bool = True,
                    messages: list[dict] | None = None) -> GuardDecision:
        if direction not in {"input", "output"} or not isinstance(text, str):
            raise ValueError("Guard direction and text are required")
        if self.policy:
            evaluate = self.policy.evaluate if direction == "input" else self.policy.evaluate_output
            if not evaluate(text, identity.roles).allowed:
                return GuardDecision(False, "", "BLOCK", "insufficient_scope", 403)
        enabled = input_enabled if direction == "input" else output_enabled
        if not enabled:
            return GuardDecision(True, text, "SKIPPED")
        try:
            if direction == "input":
                result = await self.filter_input(text=text, user_id=identity.user_id,
                                                 roles=list(identity.roles), use_ml=True,
                                                 **({"messages": messages} if messages else {}))
                blocked = _field(result, "blocked")
                if not isinstance(blocked, bool):
                    return GuardDecision(False, "", "BLOCK", "invalid_filter_response", 503)
                if messages:
                    conversation = (_field(result, "layers", {}) or {}).get("conversation", {})
                    if conversation.get("message_count") != len(messages) or not isinstance(conversation.get("blocked"), bool):
                        return GuardDecision(False, "", "BLOCK", "invalid_conversation_response", 503)
                if blocked or _field(result, "classification") == "MALICIOUS":
                    return GuardDecision(False, "", "BLOCK", "malicious_input", 403)
                return GuardDecision(True, text, "PASS", requires_output_guard=
                                     bool(_field(result, "requires_output_guard", False)),
                                     conversation_checked=bool(messages))
            result = await self.guard_output(text=text, user_id=identity.user_id, roles=list(identity.roles))
            return _output_decision(text, result)
        except Exception:
            return GuardDecision(False, "", "BLOCK", "guard_unavailable", 503)
