"""Conservative shipping policy normalizer using an authorized MCP result.

Business rules come from MCP, never from the request or from a keyword alone.
The result must still pass the existing Output Guard and ACL checks.
"""
import re
from typing import Any

_CURRENCY = r"50\s*(?:€|euros?)"
_PATTERNS = (
    # Keep the original 'para' outside this substitution.
    (re.compile(r"(?i)\bpedidos?\s+(?:de|a\s+partir\s+de)\s*" + _CURRENCY + r"\s*(?:o\s+m[aá]s|en\s+adelante)\b"),
     "pedidos superiores a 50 €"),
    (re.compile(r"(?i)\bpedidos?\s+(?:de|a\s+partir\s+de)\s*" + _CURRENCY + r"(?=\W|$)"),
     "pedidos superiores a 50 €"),
    (re.compile(r"(?i)(?:>=|≥)\s*" + _CURRENCY), "más de 50 €"),
    (re.compile(r"(?i)\b(?:a\s+partir\s+de|desde|al\s+menos|m[ií]nimo\s+(?:de\s+)?|igual\s+o\s+superior\s+a)\s*" + _CURRENCY),
     "con pedidos superiores a 50 €"),
    (re.compile(r"(?i)\b" + _CURRENCY + r"\s*(?:o\s+m[aá]s|en\s+adelante)\b"),
     "más de 50 €"),
)


def enforce_shipping_threshold(text: str, evidence: dict[str, Any] | None) -> tuple[str, tuple[str, ...]]:
    """Rewrite demonstrably wrong inclusivity claims only in free-shipping sentences."""
    if not isinstance(text, str) or not isinstance(evidence, dict):
        return text, ()
    policy = evidence.get("condiciones")
    if (not isinstance(policy, dict) or policy.get("umbral_inclusivo") is not False
            or policy.get("umbral_envio_gratis_eur") != 50
            or policy.get("envio_gratis_region") != "Península"):
        return text, ()
    parts = re.split(r"(\n+|(?<=[.!?])\s+)", text)
    repairs = []
    for i in range(0, len(parts), 2):
        part = parts[i]
        if not re.search(r"(?i)\b(?:env[ií]o|porte|shipping|entrega)\b", part):
            continue
        if not re.search(r"(?i)\b(?:gratis|gratuito|gratuita|free)\b", part):
            continue
        if re.search(r"(?i)\b(?:no|nunca|never|not)\b.{0,60}\b(?:env[ií]o|shipping)\b.{0,50}\b(?:gratis|free)\b", part):
            continue
        fixed = part
        for pattern, replacement in _PATTERNS:
            fixed = pattern.sub(replacement, fixed)
        if fixed != part:
            parts[i] = fixed
            repairs.append("noninclusive_free_shipping_threshold")
    return "".join(parts), tuple(repairs)
