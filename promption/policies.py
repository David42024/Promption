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
    tool_name: Optional[str]
    patterns: tuple[str, ...]
    confidence: float = 0.95


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    matched: bool
    policy_id: str
    resource: str
    tier: str
    tool_name: Optional[str]
    required_roles: tuple[str, ...]
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "matched": self.matched,
            "policy_id": self.policy_id,
            "resource": self.resource,
            "tier": self.tier,
            "tool_name": self.tool_name,
            "required_roles": list(self.required_roles),
            "confidence": self.confidence,
            "reason": self.reason,
        }


def normalize_text(text: str) -> str:
    """Normalize accents, case and whitespace without changing semantic content."""
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value.lower()).strip()


class PolicyEngine:
    """Classify a requested business resource and enforce its tier ACL."""

    def __init__(self, policies: Iterable[ResourcePolicy], *, tier_roles: dict,
                 output_excluded_policy_ids: frozenset[str] = frozenset()):
        self.tier_roles = tier_roles
        self.output_excluded_policy_ids = output_excluded_policy_ids
        self.policies = tuple(policies)
        self._compiled = tuple(
            (policy, tuple(re.compile(pattern, re.IGNORECASE) for pattern in policy.patterns))
            for policy in self.policies
        )

    def classify(self, text: str) -> Optional[ResourcePolicy]:
        normalized = normalize_text(text)
        for policy, patterns in self._compiled:
            if any(pattern.search(normalized) for pattern in patterns):
                return policy
        return None

    def _evaluate(
        self,
        text: str,
        roles: Iterable[str],
        excluded_policy_ids: frozenset[str] = frozenset(),
    ) -> PolicyDecision:
        role_set = {str(role).strip().lower() for role in roles if str(role).strip()}
        policy = self.classify(text)
        if policy and policy.policy_id in excluded_policy_ids:
            policy = None
        if policy is None:
            return PolicyDecision(
                allowed=True,
                matched=False,
                policy_id="public.general",
                resource="general_assistance",
                tier="publico",
                tool_name=None,
                required_roles=(),
                confidence=0.5,
                reason="No protected business resource was identified",
            )

        allowed_roles = self.tier_roles[policy.tier]
        allowed = bool(role_set & allowed_roles)
        required_roles = tuple(sorted(allowed_roles)) if policy.tier != "publico" else ()
        reason = (
            f"Role authorized for tier {policy.tier}"
            if allowed
            else f"Insufficient scope for tier {policy.tier}"
        )
        return PolicyDecision(
            allowed=allowed,
            matched=True,
            policy_id=policy.policy_id,
            resource=policy.resource,
            tier=policy.tier,
            tool_name=policy.tool_name,
            required_roles=required_roles,
            confidence=policy.confidence,
            reason=reason,
        )

    def evaluate(self, text: str, roles: Iterable[str]) -> PolicyDecision:
        """Evaluate an input request against every resource policy."""
        return self._evaluate(text, roles)

    def evaluate_output(self, text: str, roles: Iterable[str]) -> PolicyDecision:
        """Evaluate output scope while leaving concrete secret detection to Output Guard."""
        return self._evaluate(text, roles, self.output_excluded_policy_ids)


