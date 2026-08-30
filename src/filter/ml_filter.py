"""Layer 2 — ML filter: SentenceTransformers embeddings + Random Forest."""
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config()
_EMBED_MODEL = _CONF["model"]["embedding_model"]
_CLS_PATH = _CONF["paths"]["classifier"]


@dataclass
class MLResult:
    blocked: bool
    probability: float
    threshold: float
    layer: str = "ml"
    feature_importances: dict[str, float] = field(default_factory=dict)


class MLFilter:
    """Random Forest classifier trained on 384-d embedding vectors.

    The SentenceTransformer and the sklearn model are loaded lazily on first
    use, guarded by a lock so the FastAPI app and the dashboard can share a
    single worker safely.
    """

    _instance: "MLFilter | None" = None
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
        self.model_path = Path(model_path or _CLS_PATH)
        self.threshold = threshold if threshold is not None else float(_CONF["model"].get("confidence_threshold", 0.5))
        self._encoder = None
        self._clf = None
        self._initialized = True

    # --------------------------------------------------------------- lazy load
    def _ensure_loaded(self) -> None:
        if self._encoder is not None and self._clf is not None:
            return
        with MLFilter._lock:
            if self._encoder is not None and self._clf is not None:
                return
            logger.info("Loading embedding model '%s'…", _EMBED_MODEL)
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(_EMBED_MODEL)
            logger.info("Embedding model loaded.")

            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"Trained classifier not found: {self.model_path}. Run `python src/training/train.py` first."
                )
            import joblib
            self._clf = joblib.load(self.model_path)
            logger.info("RandomForest classifier loaded from %s", self.model_path)

    # ------------------------------------------------------------------ public
    def embed(self, texts: str | list[str]) -> np.ndarray:
        self._ensure_loaded()
        if isinstance(texts, str):
            texts = [texts]
        return np.asarray(self._encoder.encode(list(texts), normalize_embeddings=True), dtype=np.float32)

    def predict_proba(self, texts: str | list[str]) -> np.ndarray:
        """Return malicious probability in [0,1] (columns follow ``classes_``)."""
        self._ensure_loaded()
        x = self.embed(texts)
        probs = self._clf.predict_proba(x)
        pos_idx = int(np.flatnonzero(self._clf.classes_ == 1)[0])
        return probs[:, pos_idx]

    def analyze(self, text: str) -> MLResult:
        self._ensure_loaded()
        prob = float(self.predict_proba(text)[0])
        ti = self.feature_importance()
        return MLResult(
            blocked=prob >= self.threshold,
            probability=prob,
            threshold=self.threshold,
            feature_importances=ti,
        )

    def feature_importance(self, top_k: int = 384) -> dict[str, float]:
        self._ensure_loaded()
        importances = self._clf.feature_importances_
        dims = np.argsort(importances)[::-1][:top_k]
        return {f"dim_{i}": float(importances[i]) for i in dims}

    def is_trained(self) -> bool:
        return self.model_path.exists()

    @property
    def is_loaded(self) -> bool:
        return self._encoder is not None and self._clf is not None