"""Audio → text (STT) via faster-whisper. Fully local, CPU-only (tiny/base int8).

The Whisper model is loaded lazily the first time ``transcribe`` is called and
cached at module level. For the dashboard, load the model once with
``load_stt_model`` + ``st.cache_resource`` and pass it explicitly.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from src.utils.config import load_config

_CONF = load_config()
_MODEL = None


def load_stt_model(model_name: str | None = None):
    """Return the (cached) faster-whisper model."""
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        name = model_name or _CONF.get("stt", {}).get("model", "tiny")
        _MODEL = WhisperModel(name, device="cpu", compute_type="int8")
    return _MODEL


def transcribe(source: str | Path | bytes | bytearray | BinaryIO,
               language: str | None = None,
               model=None) -> str:
    """Transcribe an audio file (WAV/MP3/M4A/OGG/FLAC) to a single text string."""
    if model is None:
        model = load_stt_model()
    if isinstance(source, (bytes, bytearray)):
        source = BytesIO(source)
    segments, _ = model.transcribe(source, language=language, beam_size=1, without_timestamps=True)
    return " ".join(s.text.strip() for s in segments).strip()