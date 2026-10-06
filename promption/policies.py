"""Resource-policy engine configured by the consuming application."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

@dataclass(frozen=True)
class ResourcePolicy:
    policy_id: str
    resource: str
    tier: str
    tool_names: tuple[str, ...]
    patterns: tuple[str, ...]
    confidence: float = 0.95
    output_patterns: Optional[tuple[str, ...]] = None


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    matched: bool
    policy_id: str
    resource: str
    tier: str
    tool_names: tuple[str, ...]
    required_roles: tuple[str, ...]
    confidence: float
    reason: str
    matched_policy_ids: tuple[str, ...] = ()

    @property
    def tool_name(self) -> Optional[str]:
        return self.tool_names[0] if self.tool_names else None

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "matched": self.matched,
            "policy_id": self.policy_id,
            "resource": self.resource,
            "tier": self.tier,
            "tool_names": list(self.tool_names),
            "required_roles": list(self.required_roles),
            "confidence": self.confidence,
            "reason": self.reason,
            "matched_policy_ids": list(self.matched_policy_ids),
        }


def normalize_text(text: str) -> str:
    """Normalize accents, case and whitespace without changing semantic content."""
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value.lower()).strip()


class PolicyEngine:
    """Classify a requested business resource and enforce its tier ACL."""

    def __init__(self, policies: Iterable[ResourcePolicy], *, tier_roles: dict,
                 output_excluded_policy_ids: frozenset[str] = frozenset(),
                 allow_unmatched: bool = False):
        self.tier_roles = tier_roles
        self.allow_unmatched = allow_unmatched
        self.output_excluded_policy_ids = output_excluded_policy_ids
        self.policies = tuple(policies)
        self._compiled = tuple(
            (policy, tuple(re.compile(pattern, re.IGNORECASE) for pattern in policy.patterns))
            for policy in self.policies
        )
        self._compiled_output = tuple(
            (policy, tuple(re.compile(pattern, re.IGNORECASE)
                           for pattern in (policy.patterns if policy.output_patterns is None
                                           else policy.output_patterns)))
            for policy in self.policies
        )

    def classify(self, text: str, *, output: bool = False) -> Optional[ResourcePolicy]:
        """Return the most restrictive match for display; evaluate enforces every match."""
        matches = self.classify_all(text, output=output)
        return min(matches, key=lambda policy: len(self.tier_roles[policy.tier]), default=None)

    def classify_all(self, text: str, *, output: bool = False) -> tuple[ResourcePolicy, ...]:
        normalized = normalize_text(text)
        compiled = self._compiled_output if output else self._compiled
        return tuple(policy for policy, patterns in compiled
                     if any(pattern.search(normalized) for pattern in patterns))

    def _evaluate(
        self,
        text: str,
        roles: Iterable[str],
        excluded_policy_ids: frozenset[str] = frozenset(),
        output: bool = False,
    ) -> PolicyDecision:
        role_set = {str(role).strip().lower() for role in roles if str(role).strip()}
        matches = tuple(policy for policy in self.classify_all(text, output=output)
                        if policy.policy_id not in excluded_policy_ids)
        if not matches:
            return PolicyDecision(
                allowed=self.allow_unmatched,
                matched=False,
                policy_id="unclassified",
                resource="general_assistance",
                tier="unclassified",
                tool_names=(),
                required_roles=(),
                confidence=0.5,
                reason="No resource identified; application unmatched policy applied",
            )

        denied = tuple(policy for policy in matches if not role_set & self.tier_roles[policy.tier])
        policy = min(denied or matches, key=lambda item: len(self.tier_roles[item.tier]))
        allowed_roles = self.tier_roles[policy.tier]
        allowed = not denied
        required_roles = tuple(sorted(allowed_roles)) if policy.tier != "publico" else ()
        reason = (
            "Roles authorized for every matched resource"
            if allowed
            else f"Insufficient scope for tier {policy.tier}"
        )
        return PolicyDecision(
            allowed=allowed,
            matched=True,
            policy_id=policy.policy_id,
            resource=policy.resource,
            tier=policy.tier,
            tool_names=tuple(sorted({t for m in matches for t in m.tool_names})),
            required_roles=required_roles,
            confidence=policy.confidence,
            reason=reason,
            matched_policy_ids=tuple(item.policy_id for item in matches),
        )

    def evaluate(self, text: str, roles: Iterable[str]) -> PolicyDecision:
        """Evaluate an input request against every resource policy."""
        return self._evaluate(text, roles)

    def evaluate_output(self, text: str, roles: Iterable[str]) -> PolicyDecision:
        """Evaluate output scope while leaving concrete secret detection to Output Guard."""
        return self._evaluate(text, roles, self.output_excluded_policy_ids, output=True)


