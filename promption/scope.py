"""Evaluate application scope using a trusted policy and an injected semantic evaluator."""
import asyncio
import inspect
import json
from dataclasses import asdict, dataclass
from typing import Callable, Literal
import math
import re

from .intent import IntentAssessment, validate_intent
from .assessments import scope_assessments

CLARIFICATION_TEXT = "¿Puedes precisar qué información pública necesitas o qué tarea quieres realizar?"


def missing_reference(text, messages=None):
    previous = list(messages or [])
    if previous and previous[-1].get("role") == "user" and previous[-1].get("content") == text:
        previous.pop()
    return not previous and bool(re.fullmatch(r"(?:hazlo|h[aá]zlo|exp[oó]rtalo|contin[uú]a|eso|do it|export it|continue|that)[.!?\s]*", text.strip(), re.I))


def missing_reference_decision():
    return ScopeDecision("UNCERTAIN", "missing_information", 403,
        intent=IntentAssessment("clarification", "none", "unresolved", "none", 0, ()))


def needs_clarification(decision, *, tool=None, protection=None):
    """Offer a fixed response without authorizing generation, data access or tools."""
    from .profiles import resolve_protection
    settings = resolve_protection(protection)
    intent = decision.intent
    excluded = {"protected_information", "instruction_override", "privilege_escalation"}
    if settings.profile != "conversational":
        excluded.add("unknown")
    return ((settings.scope_ambiguity == "clarify" or decision.reason == "missing_information") and tool is None
            and decision.classification == "UNCERTAIN" and decision.reason in {"ambiguous", "missing_information"}
            and intent is not None and intent.attack in {"none", "unknown"} and intent.origin == "none"
            and intent.name not in excluded)


@dataclass(frozen=True)
class ScopeDecision:
    classification: Literal["IN_SCOPE", "OUT_OF_SCOPE", "UNCERTAIN"]
    reason: str
    status: int = 200
    model: str | None = None
    provider_calls: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    intent: IntentAssessment | None = None

    @property
    def allowed(self) -> bool:
        return self.classification == "IN_SCOPE"

    def to_dict(self) -> dict:
        result = {**asdict(self), "allowed": self.allowed}
        result["assessments"] = scope_assessments(self)
        result["control"] = "operational" if self.status >= 500 or self.reason == "scope_truncated" else "scope"
        result["injection"] = ("not_evaluated" if self.intent is None else
                               "not_detected" if self.intent.attack == "none" else
                               "uncertain" if self.intent.attack == "unknown" else "detected")
        if self.intent is not None:
            result["intent"] = self.intent.to_dict()
        else:
            result.pop("intent")
        return result


def _validated(result) -> ScopeDecision:
    data = result.to_dict() if isinstance(result, ScopeDecision) else result
    reasons = {"IN_SCOPE": {"in_scope"},
               "OUT_OF_SCOPE": {"topic_outside_scope", "system_limit"},
               "UNCERTAIN": {"ambiguous", "missing_information", "scope_timeout", "scope_unavailable", "scope_truncated", "invalid_scope_response"}}
    if (not isinstance(data, dict) or not isinstance(data.get("classification"), str)
            or not isinstance(data.get("reason"), str)
            or data["reason"] not in reasons.get(data["classification"], set())):
        return _validated({**(data if isinstance(data, dict) else {}),
                           "classification": "UNCERTAIN", "reason": "invalid_scope_response"})
    label = data["classification"]
    intent = None
    if data.get("intent") is not None:
        try:
            intent = validate_intent(data["intent"])
        except (TypeError, ValueError):
            return _validated({**data, "classification": "UNCERTAIN", "reason": "invalid_scope_response", "intent": None})
        if label == "IN_SCOPE" and (intent.attack != "none" or intent.relation == "unresolved"
                or intent.name in {"unknown", "instruction_override", "privilege_escalation"}):
            return _validated({**data, "classification": "UNCERTAIN", "reason": "invalid_scope_response", "intent": None})
    model = data.get("model")
    value = data.get("provider_calls", 0)
    calls = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    def _tok(k1, k2=None):
        v = usage.get(k1) if usage else data.get(k1)
        if v is None and k2:
            v = usage.get(k2) if usage else data.get(k2)
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None
    p_tok = _tok("prompt_tokens", "input_tokens")
    c_tok = _tok("completion_tokens", "output_tokens")
    t_tok = _tok("total_tokens")
    r_tok = _tok("reasoning_tokens")
    return ScopeDecision(
        label, data["reason"], (200 if label == "IN_SCOPE" else
                              504 if data["reason"] == "scope_timeout" else
                              503 if data["reason"] in {"scope_unavailable", "invalid_scope_response"} else 403),
        model=model, provider_calls=calls,
        prompt_tokens=p_tok, completion_tokens=c_tok, total_tokens=t_tok, reasoning_tokens=r_tok,
        intent=intent,
    )


def _request(text, system_prompt, messages, identity, tool):
    if not isinstance(system_prompt, str) or not system_prompt.strip() or len(system_prompt) > 50000:
        raise ValueError("A bounded, server-owned system prompt is required")
    if not isinstance(text, str) or not text.strip() or len(text) > 100000:
        raise ValueError("A bounded request is required")
    messages = messages or []
    if not isinstance(messages, list) or len(messages) > 128:
        raise ValueError("Scope context limit exceeded")
    total = len(text)
    context = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "tool"}:
            raise ValueError("Scope context must have an untrusted origin")
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("Scope context requires text")
        total += len(content)
        if total > 100000:
            raise ValueError("Scope context limit exceeded")
        context.append({"role": message["role"], "content": content,
                        **({"tool_name": message["tool_name"]} if message.get("tool_name") else {})})
    if tool is not None:
        total += len(json.dumps(tool))
        if total > 100000:
            raise ValueError("Scope context limit exceeded")
    return {"text": text, "system_prompt": system_prompt, "messages": context,
            "identity": {"user_id": identity.user_id, "roles": list(identity.roles),
                         "authenticated": identity.authenticated} if identity else {},
            **({"tool": tool} if tool is not None else {})}


class ScopeGuard:
    """Classify topical relevance and system limits without depending on a provider."""

    def __init__(self, evaluator: Callable):
        if not callable(evaluator):
            raise TypeError("A semantic scope evaluator is required")
        self.evaluator = evaluator

    def check(self, text: str, *, system_prompt: str, identity=None,
              messages: list[dict] | None = None, tool: dict | None = None) -> ScopeDecision:
        request = _request(text, system_prompt, messages, identity, tool)
        try:
            return _validated(self.evaluator(request))
        except Exception:
            return ScopeDecision("UNCERTAIN", "scope_unavailable", 503)


class AsyncScopeGuard(ScopeGuard):
    """Bound an asynchronous classifier and fail closed on errors or invalid verdicts."""

    def __init__(self, evaluator: Callable, *, timeout_seconds: float = 30):
        super().__init__(evaluator)
        if timeout_seconds <= 0:
            raise ValueError("A positive scope timeout is required")
        self.timeout_seconds = timeout_seconds

    async def check(self, text: str, *, system_prompt: str, identity=None,
                    messages: list[dict] | None = None, tool: dict | None = None) -> ScopeDecision:
        try:
            async def evaluate():
                request = _request(text, system_prompt, messages, identity, tool)
                request["timeout"] = self.timeout_seconds
                result = self.evaluator(request)
                return await result if inspect.isawaitable(result) else result
            return _validated(await asyncio.wait_for(evaluate(), self.timeout_seconds))
        except (asyncio.TimeoutError, TimeoutError):
            return ScopeDecision("UNCERTAIN", "scope_timeout", 504)
        except Exception:
            return ScopeDecision("UNCERTAIN", "scope_unavailable", 503)


def _context_decision(decision, messages, minimum_confidence, tool=None):
    from dataclasses import replace
    if decision.reason in {"scope_timeout", "scope_unavailable", "scope_truncated", "invalid_scope_response"}:
        return decision
    intent = decision.intent
    if intent is None:
        return replace(decision, classification="UNCERTAIN", reason="invalid_scope_response", status=503)
    evidence = messages or []
    has_proposal = (isinstance(tool, dict) and isinstance(tool.get("name"), str)
                    and bool(tool["name"].strip()) and "input" in tool)
    if (any(index >= len(evidence) for index in intent.evidence)
            or (intent.relation == "follow_up" and not intent.evidence)
            or (intent.origin in {"tool", "mixed"} and not has_proposal and not any(
                evidence[index].get("role") == "tool" for index in intent.evidence))):
        return replace(decision, classification="UNCERTAIN", reason="invalid_scope_response", status=503,
                       intent=None)
    if decision.reason == "missing_information":
        return decision
    if intent.confidence < minimum_confidence or intent.relation == "unresolved" or intent.attack == "unknown":
        return replace(decision, classification="UNCERTAIN", reason="ambiguous", status=403)
    return decision


class ContextScopeGuard(ScopeGuard):
    """Require canonical intent and provenance alongside policy compliance in one evaluation."""

    def __init__(self, evaluator: Callable, *, minimum_confidence: float = 0.8):
        super().__init__(evaluator)
        if (isinstance(minimum_confidence, bool) or not isinstance(minimum_confidence, (int, float))
                or not math.isfinite(minimum_confidence) or not 0 <= minimum_confidence <= 1):
            raise ValueError("Minimum confidence must be within [0, 1]")
        self.minimum_confidence = minimum_confidence

    def check(self, text: str, *, system_prompt: str, identity=None,
              messages: list[dict] | None = None, tool: dict | None = None) -> ScopeDecision:
        decision = super().check(text, system_prompt=system_prompt, identity=identity, messages=messages, tool=tool)
        return _context_decision(decision, messages, self.minimum_confidence, tool)


class AsyncContextScopeGuard(AsyncScopeGuard):
    """Asynchronous intent and scope evaluation with deadlines and strict evidence validation."""

    def __init__(self, evaluator: Callable, *, timeout_seconds: float = 30, minimum_confidence: float = 0.8):
        super().__init__(evaluator, timeout_seconds=timeout_seconds)
        if (isinstance(minimum_confidence, bool) or not isinstance(minimum_confidence, (int, float))
                or not math.isfinite(minimum_confidence) or not 0 <= minimum_confidence <= 1):
            raise ValueError("Minimum confidence must be within [0, 1]")
        self.minimum_confidence = minimum_confidence

    async def check(self, text: str, *, system_prompt: str, identity=None,
                    messages: list[dict] | None = None, tool: dict | None = None) -> ScopeDecision:
        decision = await super().check(text, system_prompt=system_prompt, identity=identity, messages=messages, tool=tool)
        return _context_decision(decision, messages, self.minimum_confidence, tool)
