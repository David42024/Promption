"""Shared consumption contract and metrics aggregator for Promption and Chat Service."""
from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any, Dict, Optional, Set


@dataclass
class UsageEvent:
    event_id: str
    call_type: str  # "generation", "scope", "tool", etc.
    provider_calls: int = 1
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    has_usage: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetricsAggregator:
    """Aggregates provider calls and token usage according to the shared contract.
    
    Rules:
    1. Explicit 0 is valid data.
    2. None means unknown; does not equal zero.
    3. Omitted operations do not introduce unknown consumption.
    4. An initiated call without usage makes the corresponding field incomplete.
    5. reasoning_tokens is not added to total_tokens again.
    6. Coverage is evaluated per field.
    7. Deduplicates by event_id to prevent double-counting across services.
    8. Does not log or expose sensitive inputs or secrets.
    """

    def __init__(self):
        self._events: Dict[str, UsageEvent] = {}
        self._seen_ids: Set[str] = set()
        self._summaries: Dict[str, Dict[str, Any]] = {}
        self.generation_calls = 0
        self.scope_calls = 0
        self.failed_calls = 0

    def add_call(
        self,
        call_type: str,
        calls: int = 1,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        reasoning_tokens: Optional[int] = None,
        has_usage: Optional[bool] = None,
        failed: bool = False,
        event_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Register an initiated call. Returns True if recorded, False if duplicate event_id."""
        if event_id:
            if event_id in self._seen_ids:
                return False
            self._seen_ids.add(event_id)
        else:
            event_id = f"{call_type}-{len(self._events) + 1}"

        if has_usage is None:
            has_usage = any(t is not None for t in (prompt_tokens, completion_tokens, total_tokens, reasoning_tokens))

        calls_cnt = max(0, int(calls)) if calls is not None else 0
        if call_type == "scope":
            self.scope_calls += calls_cnt
        elif call_type == "generation":
            self.generation_calls += calls_cnt
        if failed:
            self.failed_calls += calls_cnt

        evt = UsageEvent(
            event_id=event_id,
            call_type=call_type,
            provider_calls=calls_cnt,
            prompt_tokens=prompt_tokens if prompt_tokens is not None else None,
            completion_tokens=completion_tokens if completion_tokens is not None else None,
            total_tokens=total_tokens if total_tokens is not None else None,
            reasoning_tokens=reasoning_tokens if reasoning_tokens is not None else None,
            has_usage=bool(has_usage),
            metadata=metadata or {},
        )
        self._events[event_id] = evt
        return True

    def add_summary(self, summary: Dict[str, Any], event_id: str) -> bool:
        """Merge a remote attempt without flattening its usage coverage."""
        if event_id in self._seen_ids:
            return False
        calls = int(summary["provider_calls"])
        scope = int(summary.get("scope_calls", 0))
        generation = int(summary.get("generation_calls", calls - scope))
        failed = int(summary.get("failed_calls", 0))
        coverage = summary["usage_coverage"]
        with_usage = int(coverage["calls_with_usage"])
        without_usage = int(coverage["calls_without_usage"])
        if min(calls, scope, generation, failed, with_usage, without_usage) < 0:
            raise ValueError("Usage counters must be nonnegative")
        if scope + generation != calls or with_usage + without_usage != calls or failed > calls:
            raise ValueError("Usage counters must describe the same population")
        self._seen_ids.add(event_id)
        self._summaries[event_id] = deepcopy(summary)
        self.scope_calls += scope
        self.generation_calls += generation
        self.failed_calls += failed
        return True

    def summary(self) -> Dict[str, Any]:
        """Compute the metrics summary with totals, subtotals, and coverage breakdown."""
        total_provider_calls = self.generation_calls + self.scope_calls

        # Subtotals of actually known values
        known_p: Optional[int] = None
        known_c: Optional[int] = None
        known_t: Optional[int] = None
        known_r: Optional[int] = None

        # Field completeness flags: True if all initiated calls with provider_calls > 0 provided a known value
        fields_complete = {
            "prompt_tokens": True,
            "completion_tokens": True,
            "total_tokens": True,
            "reasoning_tokens": True,
        }

        calls_with_usage = 0
        calls_without_usage = 0

        for evt in self._events.values():
            if evt.provider_calls <= 0:
                continue

            if evt.has_usage:
                calls_with_usage += evt.provider_calls
            else:
                calls_without_usage += evt.provider_calls

            # Prompt tokens
            if evt.prompt_tokens is not None:
                known_p = (known_p or 0) + evt.prompt_tokens
            else:
                fields_complete["prompt_tokens"] = False

            # Completion tokens
            if evt.completion_tokens is not None:
                known_c = (known_c or 0) + evt.completion_tokens
            else:
                fields_complete["completion_tokens"] = False

            # Total tokens
            if evt.total_tokens is not None:
                known_t = (known_t or 0) + evt.total_tokens
            elif evt.prompt_tokens is not None and evt.completion_tokens is not None:
                calc_t = evt.prompt_tokens + evt.completion_tokens
                known_t = (known_t or 0) + calc_t
            else:
                fields_complete["total_tokens"] = False

            # Reasoning tokens
            if evt.reasoning_tokens is not None:
                known_r = (known_r or 0) + evt.reasoning_tokens
            else:
                fields_complete["reasoning_tokens"] = False

        known = {"prompt_tokens": known_p, "completion_tokens": known_c,
                 "total_tokens": known_t, "reasoning_tokens": known_r}
        for remote in self._summaries.values():
            coverage = remote["usage_coverage"]
            calls_with_usage += coverage["calls_with_usage"]
            calls_without_usage += coverage["calls_without_usage"]
            if remote["provider_calls"] == 0:
                continue
            for name in fields_complete:
                value = remote["known_usage"].get(name)
                if value is not None:
                    known[name] = (known[name] or 0) + value
                fields_complete[name] = fields_complete[name] and coverage["fields"].get(name, False)
        known_p, known_c, known_t, known_r = (known[name] for name in fields_complete)

        if total_provider_calls == 0:
            # Omitted operations do not invalidate coverage
            is_complete = True
            for k in fields_complete:
                fields_complete[k] = True
            full_p = None
            full_c = None
            full_t = None
            full_r = None
        else:
            is_complete = all(fields_complete.values())
            full_p = known_p if fields_complete["prompt_tokens"] else None
            full_c = known_c if fields_complete["completion_tokens"] else None
            full_t = known_t if fields_complete["total_tokens"] else None
            full_r = known_r if fields_complete["reasoning_tokens"] else None

        return {
            "provider_calls": total_provider_calls,
            "generation_calls": self.generation_calls,
            "scope_calls": self.scope_calls,
            "failed_calls": self.failed_calls,
            "prompt_tokens": full_p,
            "completion_tokens": full_c,
            "total_tokens": full_t,
            "reasoning_tokens": full_r,
            "known_usage": {
                "prompt_tokens": known_p,
                "completion_tokens": known_c,
                "total_tokens": known_t,
                "reasoning_tokens": known_r,
            },
            "usage_coverage": {
                "calls_total": total_provider_calls,
                "calls_with_usage": calls_with_usage,
                "calls_without_usage": calls_without_usage,
                "is_complete": is_complete,
                "fields": fields_complete,
            },
        }
