"""Bounded, non-executing inspection of base64 instructions in untrusted text.

Never replaces the original text, grants authority or evaluates decoded source code.
Only treats an encoded instruction as a hard veto if a nearby instruction
explicitly requests execution AND the decoded text attacks higher-priority rules.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass

MAX_TEXT_CHARS = 100_000
MAX_CANDIDATES = 4
MAX_PAYLOAD_CHARS = 4096
MAX_DECODED_BYTES = 4096

_DECODE = re.compile(r"\b(?:decodific\w*|decod\w*|decode|decoding)\b", re.I)
_EXECUTE = re.compile(r"\b(?:ejecut\w*|ejec[úu]t\w*|obedece|obedezcas|sigue|aplica|execute|executing|obey|follow)\b", re.I)
_NEGATED_EXECUTE = re.compile(r"\b(?:no|nunca|sin|not|never|do\s+not|don't)\s+(?:ejecut\w*|ejec[úu]t\w*|obed\w*|seguir|execute|executing|obey|follow)\b", re.I)
_ENCODING = re.compile(r"\b(?:base\s*64|b64)\b", re.I)
_REVERSE = re.compile(r"\b(?:al\s+rev[eé]s|revi[eé]rt\w*|invert\w*|reverse[sd]?|backwards)\b", re.I)
_CANDIDATE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{16,4096}={0,2}(?![A-Za-z0-9+/=])")
_OVERRIDE = re.compile(
    r"\b(?:ignore|disregard|override|bypass|forget)\b.{0,65}"
    r"\b(?:instructions?|rules?|polic(?:y|ies)|system|developer|safety|safeguards?)\b"
    r"|\b(?:ignora|olvida|desactiva|anula|omite|saltate|s[áa]ltate)\b.{0,65}"
    r"\b(?:instrucciones?|reglas?|pol[ií]ticas?|sistema|seguridad)\b"
    r"|\b(?:reveal|print|disclose|show|dump|expose)\b.{0,50}"
    r"\b(?:system\s+(?:prompt|message)|private\s+key|secret\s+(?:key|token)|internal\s+instructions?)\b"
    r"|\b(?:revela|muestra|imprime|exp[oó]n|entrega)\b.{0,55}"
    r"\b(?:mensaje\s+del\s+sistema|prompt\s+del\s+sistema|clave\s+privada|instrucciones\s+internas)\b",
    re.I | re.S,
)

@dataclass(frozen=True)
class EncodedEvidence:
    encoded_span: tuple[int, int]
    decoded_bytes: int
    decoded_sha256_prefix: str
    encoding: str = "base64"


def inspect_encoded_instructions(text: str) -> list[EncodedEvidence]:
    """Return bounded evidence, never the decoded content itself.

    Only examines decoded text if the user explicitly asks to both decode and
    carry out a nearby base64 instruction. Unsupported/binary payloads are not
    considered proof of an instruction override.
    """
    if not isinstance(text, str) or not text or len(text) > MAX_TEXT_CHARS:
        return []
    results = []
    for cue in list(_REVERSE.finditer(text))[:MAX_CANDIDATES]:
        local = text[max(0, cue.start() - 125):min(len(text), cue.end() + 125)]
        if not _EXECUTE.search(_NEGATED_EXECUTE.sub("", local)):
            continue
        tail_start = text.find(":", cue.end(), min(len(text), cue.end() + 160))
        if tail_start < 0:
            continue
        tail_start += 1
        tail_end = min(len(text), tail_start + MAX_PAYLOAD_CHARS)
        payload = text[tail_start:tail_end].split("\n", 1)[0].strip()
        decoded = payload[::-1]
        data = decoded.encode("utf-8")
        if len(data) <= MAX_DECODED_BYTES and _OVERRIDE.search(decoded):
            evidence = EncodedEvidence((tail_start, tail_start + len(text[tail_start:tail_end].split("\n", 1)[0])),
                                       len(data), hashlib.sha256(data).hexdigest()[:12], "reverse")
            if evidence not in results:
                results.append(evidence)
        if len(results) >= MAX_CANDIDATES:
            return results
    inspected = 0
    for encoding in _ENCODING.finditer(text):
        # All three components must be close, regardless of word order.
        start = max(0, encoding.start() - 125)
        end = min(len(text), encoding.end() + 125)
        local = text[start:end]
        if not (_DECODE.search(local) and _EXECUTE.search(_NEGATED_EXECUTE.sub("", local))):
            continue
        for match in _CANDIDATE.finditer(text, encoding.end(), min(len(text), encoding.end() + 160)):
            token = match.group(0)
            if len(token) > MAX_PAYLOAD_CHARS:
                continue
            inspected += 1
            if inspected > MAX_CANDIDATES:
                return results
            try:
                data = base64.b64decode(token, validate=True)
                if not data or len(data) > MAX_DECODED_BYTES:
                    continue
                decoded = data.decode("utf-8", errors="strict")
            except (ValueError, UnicodeError, binascii.Error):
                continue
            if _OVERRIDE.search(decoded):
                results.append(EncodedEvidence(match.span(), len(data), hashlib.sha256(data).hexdigest()[:12]))
                if len(results) >= MAX_CANDIDATES:
                    return results
                break
    return results
