"""Output Guard: política PASS/REDACT/BLOCK y redacción segura."""
from __future__ import annotations

from .types import Action, Finding, GuardResult, Severity

BLOCK_MESSAGE = "No puedo mostrar información sensible o credenciales en la respuesta."
REDACTED = "[REDACTED]"

_RISK = {Severity.LOW: 0.25, Severity.MEDIUM: 0.6, Severity.HIGH: 0.85, Severity.CRITICAL: 0.98}
_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def _action_for(findings: list[Finding]) -> str:
    if any(f.severity == Severity.CRITICAL for f in findings):
        return Action.BLOCK
    if any(f.severity == Severity.HIGH for f in findings):
        return Action.REDACT if len(findings) == 1 else Action.BLOCK
    if any(f.severity == Severity.MEDIUM for f in findings):
        return Action.REDACT
    return Action.PASS


def apply_policy(text: str, findings: list[Finding]) -> GuardResult:
    if not findings:
        return GuardResult(action=Action.PASS, risk=0.02)
    top = max(f.severity for f in findings)
    risk = min(0.99, _RISK[top] + 0.02 * (len(findings) - 1))
    cats = sorted({f.category for f in findings})
    action = _action_for(findings)
    if action == Action.BLOCK:
        return GuardResult(action=action, risk=risk, categories=cats, matches=len(findings))
    redacted = text
    for fnd in sorted(findings, key=lambda f: f.redacted_span[0], reverse=True):
        a, b = fnd.redacted_span
        redacted = redacted[:a] + REDACTED + redacted[b:]
    return GuardResult(action=action, risk=risk, categories=cats,
                       matches=len(findings), redacted_response=redacted)
