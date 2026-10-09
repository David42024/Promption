"""Evaluate application scope using a trusted policy and an injected semantic evaluator."""
import asyncio
import inspect
import json
from dataclasses import asdict, dataclass
from typing import Callable, Literal


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

    @property
    def allowed(self) -> bool:
        return self.classification == "IN_SCOPE"

    def to_dict(self) -> dict:
        return {**asdict(self), "allowed": self.allowed}


def _validated(result) -> ScopeDecision:
    data = result.to_dict() if isinstance(result, ScopeDecision) else result
    reasons = {"IN_SCOPE": {"in_scope"},
               "OUT_OF_SCOPE": {"topic_outside_scope", "system_limit"},
               "UNCERTAIN": {"ambiguous", "scope_timeout", "scope_unavailable", "scope_truncated", "invalid_scope_response"}}
    if (not isinstance(data, dict) or not isinstance(data.get("classification"), str)
            or not isinstance(data.get("reason"), str)
            or data["reason"] not in reasons.get(data["classification"], set())):
        return _validated({**(data if isinstance(data, dict) else {}),
                           "classification": "UNCERTAIN", "reason": "invalid_scope_response"})
    label = data["classification"]
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
        prompt_tokens=p_tok, completion_tokens=c_tok, total_tokens=t_tok, reasoning_tokens=r_tok
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
