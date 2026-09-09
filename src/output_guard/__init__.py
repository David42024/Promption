"""Output Guard: capa independiente anti-fuga de secretos en respuestas del LLM."""
from .detector import scan
from .guard import BLOCK_MESSAGE, guard_response
from .types import Action, Finding, GuardResult, Severity

__all__ = ["scan", "guard_response", "BLOCK_MESSAGE",
           "Action", "Finding", "GuardResult", "Severity"]
