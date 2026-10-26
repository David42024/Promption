"""Local and asynchronous guard pipelines independent of web frameworks."""
import logging
import math
from dataclasses import dataclass, replace
from typing import Any, Callable, Literal

from .profiles import resolve_protection
from .assessments import assess, empty_assessments, merge_assessments, scope_assessments

logger = logging.getLogger(__name__)


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
    conversation: dict | None = None
    protection: dict | None = None
    direction: str = "input"
    requires_scope_review: bool = False
    assessments: dict | None = None
    input_risk_score: float | None = None

    @property
    def control(self):
        if self.status >= 500 or self.reason in {"invalid_input", "conversation_limit", "scope_truncated"}:
            return "operational"
        if self.reason == "insufficient_scope":
            return "authorization"
        if self.assessments and self.assessments["injection"]["state"] == "denied":
            return "injection"
        if self.scope is not None:
            return "scope"
        if self.reason in {"malicious_input", "uncertain_input"} or self.requires_output_guard:
            return "injection"
        if self.direction == "output":
            return "output"
        return "input"

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "text": self.text, "action": self.action,
                "reason": self.reason, "requires_output_guard": self.requires_output_guard,
                "conversation_checked": self.conversation_checked, "scope": self.scope,
                "control": self.control,
                "assessments": self.assessments or empty_assessments(),
                "requires_scope_review": self.requires_scope_review,
                "input_risk_score": self.input_risk_score,
                **({"protection": self.protection} if self.protection is not None else {}),
                **({"conversation": self.conversation} if self.conversation is not None else {})}


def _field(result: Any, key: str, default: Any = None) -> Any:
    return result.get(key, default) if isinstance(result, dict) else getattr(result, key, default)


def _input_guard_decision(text: str, result: Any, *, message_count: int = 0,
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


def input_guard_decision(text: str, result: Any, *, message_count: int = 0,
                         output_enabled: bool = True, protection=None, enforce_risk_policy: bool = True) -> GuardDecision:
    settings = resolve_protection(protection)
    decision = _input_guard_decision(text, result, message_count=message_count, output_enabled=output_enabled)
    layers = _field(result, "layers", {})
    conversation = layers.get("conversation", {}) if isinstance(layers, dict) else {}
    conversation = conversation if isinstance(conversation, dict) else {}
    scope_flags = (_field(result, "requires_scope_review", False), conversation.get("requires_scope_review", False))
    scope_review = any(scope_flags)
    if any(not isinstance(flag, bool) for flag in scope_flags):
        decision = GuardDecision(False, "", "BLOCK", "invalid_filter_response", 503)
        scope_review = False
    if scope_review and decision.allowed:
        decision = replace(decision, requires_output_guard=True, action="GUARDED")
        if not output_enabled:
            decision = replace(decision, allowed=False, text="", action="BLOCK", reason="output_guard_required", status=503)
    scores = [_field(result, "input_risk_score"), conversation.get("input_risk_score")]
    if any(score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))
           or not math.isfinite(score) or not 0 <= score <= 1) for score in scores):
        decision = GuardDecision(False, "", "BLOCK", "invalid_filter_response", 503)
        risk_score = None
    else:
        risk_score = max((score for score in scores if score is not None), default=None)
    if enforce_risk_policy and decision.allowed and risk_score is not None and risk_score >= settings.review_block_threshold:
        decision = replace(decision, allowed=False, text="", action="BLOCK", reason="risk_policy_veto", status=403,
                           requires_output_guard=True)
    if decision.allowed and decision.requires_output_guard and settings.input_uncertainty == "block":
        decision = replace(decision, allowed=False, text="", action="BLOCK", reason="uncertain_input", status=403)
    state = "error" if decision.status >= 500 else "denied" if decision.reason == "malicious_input" else "uncertain" if decision.requires_output_guard else "allowed"
    assessments = assess(None, "injection", state, decision.reason or ("review_required" if state == "uncertain" else "no_attack_detected"), "input_filter")
    return replace(decision, protection=settings.to_dict(), assessments=assessments, requires_scope_review=scope_review,
                   input_risk_score=risk_score)


def _apply_scope(decision, scope, protection, output_enabled):
    from .scope import CLARIFICATION_TEXT, needs_clarification
    assessments = scope_assessments(scope, decision.assessments)
    common = {"scope": scope.to_dict(), "assessments": assessments, "protection": protection.to_dict()}
    if assessments["injection"]["state"] == "denied":
        return GuardDecision(False, "", "BLOCK", "malicious_input", 403, **common)
    if not scope.allowed:
        if output_enabled and needs_clarification(scope, protection=protection):
            return GuardDecision(False, CLARIFICATION_TEXT, "CLARIFY", scope.reason, 200,
                                 requires_output_guard=True, **common)
        return GuardDecision(False, "", "BLOCK", "out_of_scope" if scope.classification == "OUT_OF_SCOPE"
                             else scope.reason, scope.status, **common)
    return replace(decision, requires_scope_review=False, **common)


class Promption:
    """Use the input filter, application ACL and Output Guard in process."""

    def __init__(self, *, input_filter=None, policy=None, admin_role: str = "admin", scope_guard=None,
                 protection=None):
        from .filter.ensemble_filter import EnsembleFilter
        self.input_filter = input_filter if input_filter is not None else EnsembleFilter()
        self.policy = policy
        self.admin_role = admin_role
        self.scope_guard = scope_guard
        self.protection = resolve_protection(protection)

    def check_input(self, text: str, identity: Identity | None = None, *, use_ml: bool = True,
                    system_prompt: str | None = None, messages: list[dict] | None = None,
                    output_enabled: bool = False, isolate_history: bool = False) -> GuardDecision:
        """Inspect current input and supplied history; guarded inputs require output protection."""
        from .conversation_guard import ConversationGuard, ConversationLimitError, validate_messages
        identity = identity or Identity("anonymous")
        assessments = empty_assessments()
        if not isinstance(text, str):
            return GuardDecision(False, "", "BLOCK", "invalid_input", 400, protection=self.protection.to_dict())
        if self.policy:
            permitted = self.policy.evaluate(text, identity.roles).allowed
            assessments = assess(assessments, "authorization", "allowed" if permitted else "denied",
                                 "policy_allowed" if permitted else "policy_denied", "resource_policy")
            if not permitted:
                return GuardDecision(False, "", "BLOCK", "insufficient_scope", 403,
                                     protection=self.protection.to_dict(), assessments=assessments)
        conversation = None
        evidence = messages
        try:
            if messages is not None:
                validated = validate_messages(messages)
                evidence = [{"role": item.role, "content": item.content,
                             **({"tool_name": item.tool_name} if item.tool_name else {})}
                            for item in validated]
                if not evidence or evidence[-1]["role"] != "user" or evidence[-1]["content"] != text:
                    evidence.append({"role": "user", "content": text})
                conversation = ConversationGuard(self.input_filter).analyze(
                    evidence, roles=list(identity.roles), use_ml=use_ml, isolate_history=isolate_history)
            result = self.input_filter.analyze(text, use_ml=use_ml, roles=list(identity.roles))
        except ConversationLimitError:
            return GuardDecision(False, "", "BLOCK", "conversation_limit", 413, protection=self.protection.to_dict(),
                                 assessments=assess(assessments, "injection", "error", "conversation_limit", "input_filter"))
        except (TypeError, ValueError):
            return GuardDecision(False, "", "BLOCK", "invalid_input", 400, protection=self.protection.to_dict(),
                                 assessments=assess(assessments, "injection", "error", "invalid_input", "input_filter"))
        except Exception as e:
            logger.error("Input guard inspection failed: %s", type(e).__name__)
            return GuardDecision(False, "", "BLOCK", "guard_unavailable", 503, protection=self.protection.to_dict(),
                                 assessments=assess(assessments, "injection", "error", "guard_unavailable", "input_filter"))
        decision = input_guard_decision(text, {
            "blocked": _field(result, "blocked"), "decision": _field(result, "decision"),
            "requires_output_guard": _field(result, "requires_output_guard", False),
            "requires_scope_review": _field(result, "requires_scope_review", False),
            "input_risk_score": _field(_field(result, "ml"), "probability"),
            "layers": {"conversation": conversation.metadata()} if conversation is not None else {},
        }, message_count=len(evidence or []), output_enabled=output_enabled, protection=self.protection)
        decision = replace(decision, assessments=merge_assessments(assessments, decision.assessments))
        if not decision.allowed:
            return decision
        from .scope import missing_reference, missing_reference_decision
        if self.scope_guard is None and missing_reference(text, evidence):
            return _apply_scope(decision, missing_reference_decision(), self.protection, output_enabled)
        if decision.requires_scope_review and self.scope_guard is None:
            return replace(decision, allowed=False, text="", action="BLOCK", reason="scope_review_required", status=503)
        scope = None
        if self.scope_guard:
            try:
                scope = self.scope_guard.check(text, system_prompt=system_prompt, identity=identity,
                    messages=evidence[-1:] if conversation and conversation.isolated_history else evidence)
            except Exception:
                return replace(decision, allowed=False, text="", action="BLOCK", reason="scope_unavailable", status=503,
                    assessments=assess(decision.assessments, "scope", "error", "scope_unavailable", "scope_evaluator"))
            decision = _apply_scope(decision, scope, self.protection, output_enabled)
            if not decision.allowed:
                return decision
        return replace(decision, action="GUARDED" if decision.requires_output_guard else "ALLOWED",
                       scope=scope.to_dict() if scope else None,
                       conversation=conversation.metadata() if conversation is not None else None)

    def check_conversation(self, messages: list, identity: Identity | None = None,
                           *, use_ml: bool = True, output_enabled: bool = False) -> GuardDecision:
        from .conversation_guard import ConversationGuard, ConversationLimitError
        identity = identity or Identity("anonymous")
        try:
            result = ConversationGuard(self.input_filter).analyze(messages, roles=list(identity.roles), use_ml=use_ml)
        except ConversationLimitError:
            return GuardDecision(False, "", "BLOCK", "conversation_limit", 413, protection=self.protection.to_dict())
        except (TypeError, ValueError):
            return GuardDecision(False, "", "BLOCK", "invalid_input", 400, protection=self.protection.to_dict())
        except Exception as e:
            logger.error("Conversation guard inspection failed: %s", type(e).__name__)
            return GuardDecision(False, "", "BLOCK", "guard_unavailable", 503, protection=self.protection.to_dict())
        return input_guard_decision("", {"blocked": result.blocked,
            "requires_output_guard": result.requires_output_guard,
            "layers": {"conversation": result.metadata()}},
            message_count=result.message_count, output_enabled=output_enabled, protection=self.protection)

    def check_output(self, text: str, identity: Identity | None = None,
                     *, protected_values=()) -> GuardDecision:
        from .output_guard import guard_response
        identity = identity or Identity("anonymous")
        assessments = empty_assessments()
        if self.policy:
            permitted = self.policy.evaluate_output(text, identity.roles).allowed
            assessments = assess(assessments, "authorization", "allowed" if permitted else "denied",
                                 "policy_allowed" if permitted else "policy_denied", "resource_policy")
            if not permitted:
                return GuardDecision(False, "", "BLOCK", "insufficient_scope", 403, protection=self.protection.to_dict(), assessments=assessments)
        result = guard_response(text, admin_mode=self.admin_role in identity.roles,
                                protected_values=protected_values)
        return replace(output_guard_decision(text, result), protection=self.protection.to_dict(), assessments=assessments)


def output_guard_decision(text: str, result: Any) -> GuardDecision:
    """Validate output actions and redact without falling back to the original response."""
    action = _field(result, "action")
    if action == "BLOCK":
        return GuardDecision(False, "", "BLOCK", "sensitive_output", 403, direction="output")
    if action == "REDACT":
        redacted = _field(result, "redacted_response")
        if not isinstance(redacted, str):
            return GuardDecision(False, "", "BLOCK", "invalid_guard_response", 503, direction="output")
        return GuardDecision(True, redacted, "REDACT", direction="output")
    if action != "PASS":
        return GuardDecision(False, "", "BLOCK", "invalid_guard_response", 503, direction="output")
    return GuardDecision(True, text, "PASS", direction="output")


class AsyncGuardPipeline:
    """Compose remote/local checks and ACL, failing closed on guard service errors."""

    def __init__(self, *, filter_input: Callable, guard_output: Callable, policy=None, scope_guard=None,
                 protection=None, defer_scope_review: bool = False):
        if type(defer_scope_review) is not bool:
            raise ValueError("defer_scope_review must be a server-owned boolean")
        self.filter_input = filter_input
        self.guard_output = guard_output
        self.policy = policy
        self.scope_guard = scope_guard
        self.protection = resolve_protection(protection)
        self.defer_scope_review = defer_scope_review

    async def check(self, text: str, direction: Literal["input", "output"], identity: Identity,
                    *, input_enabled: bool = True, output_enabled: bool = True,
                    messages: list[dict] | None = None, system_prompt: str | None = None,
                    isolate_history: bool = False) -> GuardDecision:
        if direction not in {"input", "output"} or not isinstance(text, str):
            raise ValueError("Guard direction and text are required")
        assessments = empty_assessments()
        if self.policy:
            evaluate = self.policy.evaluate if direction == "input" else self.policy.evaluate_output
            permitted = evaluate(text, identity.roles).allowed
            assessments = assess(assessments, "authorization", "allowed" if permitted else "denied",
                                 "policy_allowed" if permitted else "policy_denied", "resource_policy")
            if not permitted:
                return GuardDecision(False, "", "BLOCK", "insufficient_scope", 403, protection=self.protection.to_dict(), assessments=assessments)
        enabled = input_enabled if direction == "input" else output_enabled
        if not enabled and not (direction == "input" and self.scope_guard):
            return GuardDecision(True, text, "SKIPPED", protection=self.protection.to_dict(), assessments=assessments)
        active_control = "injection"
        active_source = "input_filter"
        try:
            if direction == "input":
                decision = GuardDecision(True, text, "SKIPPED", protection=self.protection.to_dict(), assessments=assessments)
                if enabled:
                    result = await self.filter_input(text=text, identity=identity, use_ml=True,
                                                     **({"messages": messages} if messages else {}),
                                                     **({"isolate_history": True} if isolate_history else {}))
                    decision = input_guard_decision(text, result, message_count=len(messages or []),
                                                    output_enabled=output_enabled, protection=self.protection,
                                                    enforce_risk_policy=not self.defer_scope_review)
                    decision = replace(decision, assessments=merge_assessments(assessments, decision.assessments))
                    if not decision.allowed:
                        return decision
                    layers = _field(result, "layers", {})
                    if isinstance(layers, dict) and isinstance(layers.get("conversation"), dict):
                        decision = replace(decision, conversation=layers["conversation"])
                from .scope import missing_reference, missing_reference_decision
                if self.scope_guard is None and missing_reference(text, messages):
                    return _apply_scope(decision, missing_reference_decision(), self.protection, output_enabled)
                scope = None
                if decision.requires_scope_review and self.scope_guard is None and not self.defer_scope_review:
                    return replace(decision, allowed=False, text="", action="BLOCK", reason="scope_review_required", status=503)
                if self.scope_guard:
                    active_control, active_source = "scope", "scope_evaluator"
                    assessments = decision.assessments
                    scope = await self.scope_guard.check(text, system_prompt=system_prompt,
                                                         identity=identity, messages=messages)
                    decision = _apply_scope(decision, scope, self.protection, output_enabled)
                return decision
            result = await self.guard_output(text=text, identity=identity)
            return replace(output_guard_decision(text, result), protection=self.protection.to_dict(), assessments=assessments)
        except Exception:
            return GuardDecision(False, "", "BLOCK", "guard_unavailable", 503, protection=self.protection.to_dict(),
                assessments=assess(assessments, active_control, "error", "guard_unavailable", active_source)
                if direction == "input" else assessments)
