"""Output Guard: punto de entrada. Inspecciona la respuesta del LLM ANTES de entregarla."""
from __future__ import annotations

from collections.abc import Iterable

from promption.utils.logger import logger

from .detector import scan
from .redactor import BLOCK_MESSAGE, apply_policy
from .types import Action, GuardResult
from .known_values import known_value_match

__all__ = ["guard_response", "scan", "GuardResult", "BLOCK_MESSAGE"]


def guard_response(text: str, admin_mode: bool = False,
                   protected_values: Iterable[str] = ()) -> GuardResult:
    """Scan known forbidden values and credential patterns without logging values."""
    category=known_value_match(text,protected_values)
    if category:
        logger.info('OutputGuard action=BLOCK category=%s matches=1',category)
        return GuardResult(action=Action.BLOCK,risk=.99,categories=[category],matches=1)
    findings = scan(text or "")
    result = apply_policy(text or "", findings, admin_mode=admin_mode)
    if findings:
        logger.info(
            "OutputGuard action=%s matches=%d categories=%s severities=%sfps=%s",
            result.action, len(findings),
            sorted({f.category for f in findings}),
            sorted({f.severity for f in findings}),
            [f.fingerprint for f in findings],
        )
    return result
