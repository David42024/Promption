"""Canonical text views shared by individual and conversation inspection."""
import html
import re
import unicodedata


def normalize_content(text: str) -> str:
    """Normalize compatibility characters, invisible format marks and whitespace."""
    text = html.unescape(unicodedata.normalize("NFKC", text))
    text = "".join(character for character in text if unicodedata.category(character) != "Cf")
    return re.sub(r"\s+", " ", text).strip()
