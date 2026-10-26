"""Bounded decoding for evidence inspection; decoded content is never executed."""
import base64
import binascii
import codecs
import re

from .evidence import adopts_quoted_instructions

_BASE64 = re.compile(r"(?<![\w+/=-])[A-Za-z0-9+/_-]{12,8192}={0,2}(?![\w+/=-])")
_HEX = re.compile(r"\b(?:0x)?([a-fA-F0-9]{24,8192})\b")


def decoded_views(text: str, *, origin="user") -> tuple[list[tuple[str, str]], bool]:
    if len(text) > 20000:
        return [], False
    adopted = origin == "tool" or adopts_quoted_instructions(text) or bool(_BASE64.fullmatch(text.strip()))
    result = []
    seen = {text}
    pending = [(text, 0)]
    total = 0
    while pending and len(result) < 8:
        value, depth = pending.pop(0)
        if depth >= 2:
            continue
        candidates = [("base64", match.group()) for match in list(_BASE64.finditer(value))[:8]]
        if re.search(r"\b(?:hex|hexadecimal|0x)[ :]*", value, re.I):
            candidates += [("hex", match.group(1)) for match in list(_HEX.finditer(value))[:8]]
        for encoding, token in candidates:
            try:
                data = bytes.fromhex(token) if encoding == "hex" else base64.b64decode(
                    token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
                decoded = data.decode("utf-8")
            except (ValueError, UnicodeError, binascii.Error):
                continue
            if (decoded in seen or not decoded.strip() or len(decoded) > 8192
                    or any(not char.isprintable() and char not in "\r\n\t" for char in decoded)):
                continue
            total += len(decoded)
            if total > 16384:
                return result, adopted
            seen.add(decoded)
            result.append((encoding, decoded))
            pending.append((decoded, depth + 1))
            if len(result) >= 8:
                break
        if len(result) < 8 and re.search(r"\brot13\s*:", value, re.I):
            token = re.split(r"\brot13\s*:", value, maxsplit=1, flags=re.I)[1][:8192]
            decoded = codecs.decode(token, "rot_13")
            if decoded not in seen and total + len(decoded) <= 16384:
                total += len(decoded)
                seen.add(decoded)
                result.append(("rot13", decoded))
                pending.append((decoded, depth + 1))
    return result, adopted
