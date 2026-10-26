"""Server-owned handling of uncertainty; profiles never override detector vetoes."""
from dataclasses import dataclass
import math

from .utils.config import load_config


@dataclass(frozen=True)
class ProtectionSettings:
    profile: str = "balanced"
    input_uncertainty: str | None = None
    scope_ambiguity: str | None = None
    review_block_threshold: float | None = None

    def __post_init__(self):
        if not isinstance(self.profile, str) or self.profile not in {"conversational", "balanced", "strict"}:
            raise ValueError("Unknown protection profile")
        defaults = ("review", "block") if self.profile == "strict" else ("review", "clarify")
        threshold = {"conversational": .85, "balanced": .75, "strict": .66}[self.profile]
        if self.review_block_threshold is None:
            object.__setattr__(self, "review_block_threshold", threshold)
        elif (isinstance(self.review_block_threshold, bool) or not isinstance(self.review_block_threshold, (int, float))
              or not math.isfinite(self.review_block_threshold) or not 0 < self.review_block_threshold < 1):
            raise ValueError("Invalid review_block_threshold")
        for name, default, allowed in (
            ("input_uncertainty", defaults[0], {"review", "block"}),
            ("scope_ambiguity", defaults[1], {"clarify", "block"}),
        ):
            value = getattr(self, name)
            if value is None:
                object.__setattr__(self, name, default)
            elif not isinstance(value, str) or value not in allowed:
                raise ValueError(f"Invalid {name}")

    def to_dict(self):
        return {"profile": self.profile, "input_uncertainty": self.input_uncertainty,
                "scope_ambiguity": self.scope_ambiguity, "review_block_threshold": self.review_block_threshold}


def resolve_protection(value=None):
    if value is None:
        value = load_config().get("protection", {})
    if isinstance(value, ProtectionSettings):
        return value
    if isinstance(value, str):
        return ProtectionSettings(profile=value)
    if not isinstance(value, dict) or set(value) - {"profile", "input_uncertainty", "scope_ambiguity", "review_block_threshold"}:
        raise ValueError("Invalid protection settings")
    return ProtectionSettings(**value)
