"""Output Guard: punto de entrada. Inspecciona la respuesta del LLM ANTES de entregarla."""
from __future__ import annotations

from src.utils.logger import logger

from .detector import scan
from .redactor import BLOCK_MESSAGE, apply_policy
from .types import GuardResult

__all__ = ["guard_response", "scan", "GuardResult", "BLOCK_MESSAGE"]


def guard_response(text: str, admin_mode: bool = False) -> GuardResult:
    """Pipeline completo: scan → policy. Log seguro (sin valores)."""
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
