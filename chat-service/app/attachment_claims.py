"""Guard against claims of fabricated file attachments; no external dependencies."""
import re

# A creation offer ("¿quieres que prepare un PDF?") is not a claim of an attachment.
# Only match completed attachment/creation statements; never infer from "listo".
_FILE_CLAIM = re.compile(
    r"(?i)\b(?:(?:te\s+)?(?:adjunté|anexé|he\s+adjuntado|hemos\s+adjuntado)|"
    r"preparé|generé|creé|he\s+(?:creado|preparado|generado)|"
    r"(?:ya\s+)?(?:est[aá]\s+adjuntado|qued[oó]\s+adjuntado))\b"
    r"[^\n.!?]{0,120}\b(?:archivo|documento|pdf|csv|txt|docx|excel|xlsx|word)\b|"
    r"\b(?:archivo|documento|pdf|csv|txt|docx|excel|xlsx|word)\b"
    r"[^\n.!?]{0,80}\b(?:est[aá]\s+adjunt[oa]|se\s+ha\s+adjuntado)\b|"
    r"\b(?:i\s+(?:have\s+)?attached|i['’]ve\s+attached|we\s+attached)\b"
    r"[^\n.!?]{0,80}\b(?:file|document|pdf|csv|txt|docx|xlsx|spreadsheet)\b"
)


def _has_false_claim(text: str) -> bool:
    for match in _FILE_CLAIM.finditer(text):
        prefix = text[max(0, match.start() - 20):match.start()]
        if re.search(r"(?i)\b(?:no|not|never|nunca)\s*$", prefix):
            continue
        return True
    return False


def _repair_unverified_attachment_reply(reply: str, *, requested: bool, verified: bool) -> tuple[str, bool]:
    """Remove unsupported file claims without discarding useful authorized prose.

    Returns (reply, functional_failure). Callers MUST run their usual output
    checks *after* this transformation. A functional failure is not a security
    block. This function cannot grant/verify an attachment.
    """
    if verified:
        return reply, False
    had_false_claim = _has_false_claim(reply)
    if not requested and not had_false_claim:
        return reply, False
    note = "No hay un archivo adjunto disponible en esta respuesta."
    # Replace only the offending sentence/line, not the entire explanation.
    parts = re.split(r"(?<=[.!?])\s+|\n+", reply.strip())
    kept = [part for part in parts if not _has_false_claim(part)]
    useful = " ".join(part.strip() for part in kept if part.strip())
    return (useful + "\n\n" + note if useful else note), bool(requested or had_false_claim)

