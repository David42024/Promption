"""Output Guard: tipos del veredicto sobre respuestas del LLM."""
from __future__ import annotations

from dataclasses import dataclass, field


class Severity:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Action:
    PASS = "PASS"
    REDACT = "REDACT"
    BLOCK = "BLOCK"


@dataclass
class Finding:
    category: str
    severity: str
    span: tuple[int, int]
    redacted_span: tuple[int, int]
    confidence: float
    fingerprint: str  # sha256 parcial del valor (nunca el secreto)


@dataclass
class GuardResult:
    action: str
    risk: float
    categories: list[str] = field(default_factory=list)
    matches: int = 0
    redacted_response: str | None = None

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "risk": round(self.risk, 3),
            "categories": self.categories,
            "matches": self.matches,
            "redacted_response": self.redacted_response,
        }
