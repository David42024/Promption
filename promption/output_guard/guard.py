"""Output Guard: punto de entrada. Inspecciona la respuesta del LLM ANTES de entregarla."""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from promption.utils.logger import logger

from .detector import scan
from .redactor import BLOCK_MESSAGE, apply_policy
from .types import Action, GuardResult

__all__ = ["guard_response", "scan", "GuardResult", "BLOCK_MESSAGE"]


def _compact(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


def guard_response(text: str, admin_mode: bool = False,
                   protected_values: Iterable[str] = ()) -> GuardResult:
    """Scan known forbidden values and credential patterns without logging values."""
    compact_text = None
    for value in protected_values:
        if not isinstance(value, str):
            raise TypeError("protected_values must contain strings")
        compact_value = _compact(value)
        if len(compact_value) < 8:
            raise ValueError("protected_values must contain at least eight letters or digits")
        if compact_text is None:
            compact_text = _compact(text or "")
        if compact_value in compact_text:
            logger.info("OutputGuard action=BLOCK categories=['known_secret'] matches=1")
            return GuardResult(action=Action.BLOCK, risk=0.99,
                               categories=["known_secret"], matches=1)
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
