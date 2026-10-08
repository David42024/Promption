"""Typed exceptions for ML classification layers."""
from __future__ import annotations


class MLError(Exception):
    """Base exception for ML filter errors."""
    code: str = "ML_ERROR"


class MLModelNotFoundError(MLError, FileNotFoundError):
    """Model artifact does not exist on disk."""
    code: str = "MODEL_NOT_FOUND"


class MLModelLoadError(MLError):
    """Model artifact exists but failed to load or deserialize (e.g. corrupted file)."""
    code: str = "LOAD_FAILED"


class MLInferenceError(MLError):
    """Model inference or feature transformation failed."""
    code: str = "INFERENCE_FAILED"
