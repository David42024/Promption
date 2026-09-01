"""PDF → text extraction for prompt-injection evaluation (text-based PDFs).

Scanned/image-only PDFs require OCR (out of scope). Extraction is lazy: each
page is read on demand and pages without extractable text are skipped.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path


def extract_pdf_pages(source: str | Path | bytes | bytearray) -> list[str]:
    """Return the non-empty text of each page of ``source`` (path or raw bytes)."""
    from pypdf import PdfReader

    if isinstance(source, (bytes, bytearray)):
        reader = PdfReader(BytesIO(source))
    else:
        reader = PdfReader(str(source))
    pages = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(text)
    return pages


def extract_pdf_text(source: str | Path | bytes | bytearray, separator: str = "\n") -> str:
    """Return the whole document as a single (page-joined) string."""
    return separator.join(extract_pdf_pages(source))