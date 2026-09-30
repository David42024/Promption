"""Local and asynchronous guard pipelines independent of web frameworks."""
from dataclasses import dataclass, replace
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
    scope: dict | None = None

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "text": self.text, "action": self.action,
                "reason": self.reason, "requires_output_guard": self.requires_output_guard,
                "conversation_checked": self.conversation_checked, "scope": self.scope}


def _field(result: Any, key: str, default: Any = None) -> Any:
    return result.get(key, default) if isinstance(result, dict) else getattr(result, key, default)


def input_guard_decision(text: str, result: Any, *, message_count: int = 0,
                         output_enabled: bool = True) -> GuardDecision:
    """Allow guarded generation only with a checked context and mandatory output protection."""
    blocked = _field(result, "blocked")
    classification = _field(result, "classification")
    if not isinstance(blocked, bool) or classification not in (None, "BENIGN", "UNCERTAIN", "MALICIOUS"):
        return GuardDecision(False, "", "BLOCK", "invalid_filter_response", 503)
    layers = _field(result, "layers", {})
    if not isinstance(layers, dict) or not isinstance(layers.get("conversation", {}), dict):
        return GuardDecision(False, "", "BLOCK", "invalid_conversation_response", 503)
    conversation = layers.get("conversation", {})
    if message_count and (type(conversation.get("message_count")) is not int
                          or conversation.get("message_count") != message_count
                          or not isinstance(conversation.get("blocked"), bool)):
        return GuardDecision(False, "", "BLOCK", "invalid_conversation_response", 503)
    if blocked or classification == "MALICIOUS" or conversation.get("blocked") is True:
        return GuardDecision(False, "", "BLOCK", "malicious_input", 403)
    decision = _field(result, "decision")
    requires_output_guard = _field(result, "requires_output_guard", False)
    if decision not in (None, "ALLOWED", "GUARDED", "BLOCKED") or not isinstance(requires_output_guard, bool):
        return GuardDecision(False, "", "BLOCK", "invalid_filter_response", 503)
    if decision == "BLOCKED":
        return GuardDecision(False, "", "BLOCK", "malicious_input", 403)
    required = (classification == "UNCERTAIN" or decision == "GUARDED"
                or requires_output_guard
                or conversation.get("requires_output_guard") is True)
    if required and not output_enabled:
        return GuardDecision(False, "", "BLOCK", "output_guard_required", 503,
                             requires_output_guard=True, conversation_checked=bool(message_count))
    return GuardDecision(True, text, "GUARDED" if required else "PASS",
                         requires_output_guard=required, conversation_checked=bool(message_count))


class Promption:
    """Use the input filter, application ACL and Output Guard in process."""

    def __init__(self, *, input_filter=None, policy=None, admin_role: str = "admin", scope_guard=None):
        from .filter.ensemble_filter import EnsembleFilter
        self.input_filter = input_filter if input_filter is not None else EnsembleFilter()
        self.policy = policy
        self.admin_role = admin_role
        self.scope_guard = scope_guard

    def check_input(self, text: str, identity: Identity | None = None, *, use_ml: bool = True,
                    system_prompt: str | None = None, messages: list[dict] | None = None) -> GuardDecision:
        identity = identity or Identity("anonymous")
        if self.policy and not self.policy.evaluate(text, identity.roles).allowed:
            return GuardDecision(False, "", "BLOCK", "insufficient_scope", 403)
        result = self.input_filter.analyze(text, use_ml=use_ml, roles=list(identity.roles))
        scope = None
        if not result.blocked and self.scope_guard:
            scope = self.scope_guard.check(text, system_prompt=system_prompt, identity=identity, messages=messages)
            if not scope.allowed:
                return GuardDecision(False, "", "BLOCK", "out_of_scope" if scope.classification == "OUT_OF_SCOPE"
                                     else scope.reason, scope.status, scope=scope.to_dict())
        return GuardDecision(not result.blocked, text if not result.blocked else "",
                             result.decision, result.blocking_reason,
                             403 if result.blocked else 200, result.requires_output_guard,
                             scope=scope.to_dict() if scope else None)

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
        return output_guard_decision(text, result)


def output_guard_decision(text: str, result: Any) -> GuardDecision:
    """Validate output actions and redact without falling back to the original response."""
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

    def __init__(self, *, filter_input: Callable, guard_output: Callable, policy=None, scope_guard=None):
        self.filter_input = filter_input
        self.guard_output = guard_output
        self.policy = policy
        self.scope_guard = scope_guard

    async def check(self, text: str, direction: Literal["input", "output"], identity: Identity,
                    *, input_enabled: bool = True, output_enabled: bool = True,
                    messages: list[dict] | None = None, system_prompt: str | None = None) -> GuardDecision:
        if direction not in {"input", "output"} or not isinstance(text, str):
            raise ValueError("Guard direction and text are required")
        if self.policy:
            evaluate = self.policy.evaluate if direction == "input" else self.policy.evaluate_output
            if not evaluate(text, identity.roles).allowed:
                return GuardDecision(False, "", "BLOCK", "insufficient_scope", 403)
        enabled = input_enabled if direction == "input" else output_enabled
        if not enabled and not (direction == "input" and self.scope_guard):
            return GuardDecision(True, text, "SKIPPED")
        try:
            if direction == "input":
                scope = None
                if self.scope_guard:
                    scope = await self.scope_guard.check(text, system_prompt=system_prompt,
                                                         identity=identity, messages=messages)
                    if not scope.allowed:
                        return GuardDecision(False, "", "BLOCK", "out_of_scope" if scope.classification == "OUT_OF_SCOPE"
                                             else scope.reason, scope.status, scope=scope.to_dict())
                if not enabled:
                    return GuardDecision(True, text, "SKIPPED", scope=scope.to_dict() if scope else None)
                result = await self.filter_input(text=text, user_id=identity.user_id,
                                                 roles=list(identity.roles), use_ml=True,
                                                 **({"messages": messages} if messages else {}))
                decision = input_guard_decision(text, result, message_count=len(messages or []),
                                                output_enabled=output_enabled)
                if scope:
                    decision = replace(decision, scope=scope.to_dict())
                return decision
            result = await self.guard_output(text=text, user_id=identity.user_id, roles=list(identity.roles))
            return output_guard_decision(text, result)
        except Exception:
            return GuardDecision(False, "", "BLOCK", "guard_unavailable", 503)
