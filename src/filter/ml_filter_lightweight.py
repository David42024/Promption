"""Lightweight ML filter using TF-IDF + LogisticRegression for Render free.

This is a much lighter alternative to SentenceTransformers + RandomForest:
- ~10-50MB vs ~200MB+
- Works on Render free (no heavy embeddings)
- Very fast inference (~10ms vs ~200ms)
"""
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config()
_MODEL_PATH = _CONF["paths"].get("lightweight_classifier", "models/lightweight_classifier.pkl")


@dataclass
class MLResult:
    blocked: bool
    probability: float
    threshold: float
    layer: str = "ml_lightweight"
    feature_importances: dict[str, float] = field(default_factory=dict)


class LightMLFilter:
    """Lightweight ML filter using TF-IDF + LogisticRegression.
    
    This filter uses a much smaller model that works on Render free.
    Load-once pattern (singleton) - model stays in memory.
    """

    _instance: "LightMLFilter | None" = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_path: str | None = None, threshold: float | None = None):
        # Singleton: __init__ may run multiple times; keep first values.
        if getattr(self, "_initialized", False):
            return
        self.model_path = Path(model_path or _MODEL_PATH)
        self.threshold = threshold if threshold is not None else float(_CONF["model"].get("confidence_threshold", 0.5))
        self._vectorizer = None
        self._classifier = None
        self._initialized = True

    def _ensure_loaded(self) -> None:
        """Load model once and keep in memory."""
        if self._vectorizer is not None and self._classifier is not None:
            return
        with LightMLFilter._lock:
            if self._vectorizer is not None and self._classifier is not None:
                return
            
            if not self.model_path.exists():
                logger.warning("Lightweight model not found at %s. ML layer will be unavailable.", self.model_path)
                raise FileNotFoundError(
                    f"Lightweight model not found: {self.model_path}. "
                    f"Run `python -m src.training.train_lightweight` first."
                )
            
            logger.info("Loading lightweight TF-IDF + LogisticRegression model from %s…", self.model_path)
            import joblib
            model_data = joblib.load(self.model_path)
            
            self._vectorizer = model_data['vectorizer']
            self._classifier = model_data['classifier']
            
            logger.info("Lightweight model loaded successfully.")
            logger.info("Model type: %s", model_data.get('model_type', 'unknown'))
            logger.info("Max features: %d", model_data.get('max_features', 'unknown'))

    def predict_proba(self, text: str) -> float:
        """Return malicious probability in [0,1]."""
        self._ensure_loaded()
        
        # TF-IDF transform
        X = self._vectorizer.transform([text])
        
        # Predict probability
        proba = self._classifier.predict_proba(X)[0]
        
        # Assuming class 1 is "injection/malicious"
        pos_idx = int(np.flatnonzero(self._classifier.classes_ == 1)[0]) if len(self._classifier.classes_) > 1 else 1
        return float(proba[pos_idx])

    def analyze(self, text: str) -> MLResult:
        """Analyze text and return ML result."""
        self._ensure_loaded()
        
        try:
            prob = self.predict_proba(text)
        except Exception as e:
            logger.error("Error in lightweight ML analysis: %s", e)
            # Fail-safe: return non-blocking on error
            return MLResult(
                blocked=False,
                probability=0.0,
                threshold=self.threshold
            )
        
        return MLResult(
            blocked=prob >= self.threshold,
            probability=prob,
            threshold=self.threshold,
            feature_importances={}
        )

    def is_trained(self) -> bool:
        """Check if model is available."""
        return self.model_path.exists()

    @property
    def is_loaded(self) -> bool:
        """Return whether vectorizer and classifier are loaded in memory."""
        return self._vectorizer is not None and self._classifier is not None


# Singleton instance
_light_filter: LightMLFilter | None = None


def get_light_ml_filter() -> LightMLFilter:
    """Get singleton LightMLFilter instance."""
    global _light_filter
    if _light_filter is None:
        _light_filter = LightMLFilter()
    return _light_filter
