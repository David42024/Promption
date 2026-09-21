"""Output Guard: escaneo determinista con validaciones estructurales."""
from __future__ import annotations

import base64
import hashlib
import json
import re

from . import patterns as _p
from .types import Finding

def _entropy_ok(value: str) -> bool:
    return len(value) >= 12 and any(c.isdigit() for c in value) and any(c.isalpha() for c in value)


def _secret_entropy_ok(value: str) -> bool:
    return (
        len(value) >= 8
        and any(c.isdigit() for c in value)
        and any(c.isalpha() for c in value)
        and ("-" in value or "_" in value or (value.lower() != value and value.upper() != value))
    )


_VALIDATORS = {"entropy": _entropy_ok, "secret_entropy": _secret_entropy_ok}

def _norm(entry: tuple) -> tuple:
    name, cat, sev, pat, conf, whole = entry[:6]
    validator = entry[6] if len(entry) > 6 else None
    return name, cat, sev, re.compile(pat), conf, whole, validator


_COMPILED = [_norm(e) for e in _p.PATTERNS]
_PLACEHOLDER = re.compile(_p.PLACEHOLDER_RE)


def _is_placeholder(value: str) -> bool:
    v = value.strip().strip("\"'")
    if not v or v.lower() in _p.PLACEHOLDER_VALUES:
        return True
    return bool(_PLACEHOLDER.fullmatch(v))


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:12]


def _jwt_valid(token: str) -> bool:
    try:
        header = token.split(".")[0] + "=="
        return isinstance(json.loads(base64.urlsafe_b64decode(header)), dict)
    except Exception:  # noqa: BLE001
        return False


def _value_span(match: re.Match) -> tuple[int, int] | None:
    try:
        return match.span(2 if match.lastindex and match.lastindex >= 2 else 1)
    except IndexError:
        return match.span(0)


def scan(text: str) -> list[Finding]:
    """Devuelve findings ordenados; nunca incluye el valor en claro salvo spans."""
    text = text or ""
    out: list[Finding] = []
    for name, cat, sev, rx, conf, whole, validator in _COMPILED:
        for m in rx.finditer(text):
            span = m.span(0) if whole else (_value_span(m) or m.span(0))
            value = text[span[0]:span[1]]
            if _is_placeholder(value):
                continue
            if validator and not _VALIDATORS[validator](value):
                continue
            sev_eff, conf_eff = sev, conf
            if name == "jwt" and _jwt_valid(value):
                sev_eff, conf_eff = "CRITICAL", 0.97
            out.append(Finding(category=cat, severity=sev_eff, span=m.span(0),
                               redacted_span=span, confidence=conf_eff,
                               fingerprint=_fingerprint(value)))
    out.sort(key=lambda f: (f.redacted_span[0], -f.redacted_span[1]))
    deduped: list[Finding] = []
    for fnd in out:
        if not any(fnd.redacted_span[0] < d.redacted_span[1] and d.redacted_span[0] < fnd.redacted_span[1]
                   for d in deduped):
            deduped.append(fnd)
    return deduped
