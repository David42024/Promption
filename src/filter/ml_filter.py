"""Layer 2 — ML filter: SentenceTransformers embeddings + Random Forest."""
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config()
_EMBED_MODEL = _CONF["model"]["embedding_model"]
_EMBED_PREFIX = str(_CONF["model"].get("embedding_prefix", "") or "")
_CLS_PATH = _CONF["paths"]["classifier"]


def prepare_texts(texts: list[str]) -> list[str]:
    """Aplica el prefijo del embedder (p. ej. 'query: ' en e5; vacío en MiniLM)."""
    if not _EMBED_PREFIX:
        return list(texts)
    return [f"{_EMBED_PREFIX}{t}" for t in texts]


@dataclass
class MLResult:
    blocked: bool
    probability: float
    threshold: float
    layer: str = "ml"
    feature_importances: dict[str, float] = field(default_factory=dict)


_SENT_SPLIT = re.compile(r"(?<=[.!?;:])\s+")


def _char_windows(text: str, size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            cut = text.rfind(" ", start, end)
            if cut > start:
                end = cut
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c.strip()] or [text]


def chunk_text(text: str, size: int = 250, overlap: int = 100) -> list[str]:
    """Split long prompts into sentence-aware overlapping windows.

    The embedding model truncates past ~256 tokens, so a single embedding
    of a long prompt is blind to attacks buried at the end. Windows break
    at sentence boundaries (never mid-attack-sentence) and carry the last
    sentence over, so the malicious sentence always lands whole in at least
    one window. Score each window, keep the worst one. No new deps.
    """
    text = text or ""
    if len(text) <= size:
        return [text]
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if len(sentences) <= 1:
        return _char_windows(text, size, overlap)
    pieces: list[str] = []
    for s in sentences:
        pieces.extend(_char_windows(s, size, overlap) if len(s) > size else [s])
    windows: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in pieces:
        add = len(p) + (1 if cur else 0)
        if cur and cur_len + add > size:
            windows.append(" ".join(cur))
            carry = cur[-1]
            cur, cur_len = ([carry], len(carry)) if len(carry) + 1 + len(p) <= size else ([], 0)
            add = len(p) + (1 if cur else 0)
        cur.append(p)
        cur_len += add
    if cur:
        windows.append(" ".join(cur))
    return windows or [text]


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

    def __init__(self, model_path: str | None = None, threshold: float | None = None,
                 chunk_chars: int | None = None, chunk_overlap: int | None = None):
        # Singleton: __init__ may run multiple times; keep first values.
        if getattr(self, "_initialized", False):
            return
        self.model_path = Path(model_path or _CLS_PATH)
        self.threshold = threshold if threshold is not None else float(_CONF["model"].get("confidence_threshold", 0.5))
        self.chunk_chars = chunk_chars if chunk_chars is not None else int(_CONF["model"].get("chunk_chars", 250))
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else int(_CONF["model"].get("chunk_overlap", 100))
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
        return np.asarray(self._encoder.encode(prepare_texts(list(texts)), normalize_embeddings=True),
                          dtype=np.float32)

    def predict_proba(self, texts: str | list[str]) -> np.ndarray:
        """Return malicious probability in [0,1] (columns follow ``classes_``)."""
        self._ensure_loaded()
        x = self.embed(texts)
        probs = self._clf.predict_proba(x)
        pos_idx = int(np.flatnonzero(self._clf.classes_ == 1)[0])
        return probs[:, pos_idx]

    def analyze(self, text: str) -> MLResult:
        self._ensure_loaded()
        chunks = chunk_text(text or "", self.chunk_chars, self.chunk_overlap)
        x = self.embed(chunks)
        probs = self._clf.predict_proba(x)
        pos_idx = int(np.flatnonzero(self._clf.classes_ == 1)[0])
        prob = float(probs[:, pos_idx].max())
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