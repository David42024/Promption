"""In-process filter for the Real-Time Testing page (no API required).

Loaded once per session via `st.cache_resource`; falls back to the
heuristic layer only if the trained ML model is missing.
"""
import time

import numpy as np
import streamlit as st

from dashboard.utils.paths import MODELS_DIR
from src.benchmark.runner import sanitize_prompt
from src.filter.heuristic_filter import HeuristicFilter, HeuristicResult
from src.utils.config import load_embedding_model_name, load_classifier_path


class _MLNull:
    probability = None
    blocked = None
    threshold = None


@st.cache_resource(show_spinner="Cargando modelo de embeddings (all-MiniLM-L6-v2)…")
def load_ml_filter():
    import joblib
    path = load_classifier_path()
    if not path.exists():
        raise FileNotFoundError(path)
    from sentence_transformers import SentenceTransformer
    enc = SentenceTransformer(load_embedding_model_name())
    clf = joblib.load(path)
    return enc, clf


def filter_text(text: str, use_ml: bool = True):
    """Returns dict with full analysis details."""
    t0 = time.perf_counter()
    heur = HeuristicFilter()
    th0 = time.perf_counter()
    hres: HeuristicResult = heur.analyze(text)
    heur_ms = (time.perf_counter() - th0) * 1000

    ml = _MLNull()
    ml_ms = 0.0
    if use_ml:
        try:
            enc, clf = load_ml_filter()
            tm0 = time.perf_counter()
            emb = np.asarray(enc.encode([text], normalize_embeddings=True), dtype=np.float32)
            prob = float(clf.predict_proba(emb)[0, int(np.flatnonzero(clf.classes_ == 1)[0])])
            ml_ms = (time.perf_counter() - tm0) * 1000
            ml = type("ML", (), {"probability": prob, "blocked": prob >= 0.5, "threshold": 0.5,
                                 "available": True})()
        except FileNotFoundError:
            ml = type("ML", (), {"probability": None, "blocked": None, "threshold": None, "available": False})()
        except Exception:
            ml = type("ML", (), {"probability": None, "blocked": None, "threshold": None, "available": False})()

    total_ms = (time.perf_counter() - t0) * 1000
    if ml.probability is None:
        score = hres.score
        blocked = hres.blocked
    else:
        score = 0.4 * hres.score + 0.6 * ml.probability
        blocked = hres.blocked or ml.blocked or score >= 0.5

    return {
        "text": text,
        "decision": "BLOCKED" if blocked else "ALLOWED",
        "blocked": bool(blocked),
        "confidence": float(score),
        "latency_ms": round(total_ms, 2),
        "sanitized": sanitize_prompt(text, hres) if blocked else text,
        "heuristic": {"blocked": hres.blocked, "score": hres.score, "threshold": hres.threshold,
                      "matched_rules": hres.matched_rules, "latency_ms": round(heur_ms, 2)},
        "ml": {"available": ml.available if hasattr(ml, "available") else ml.probability is not None,
               "blocked": ml.blocked, "probability": ml.probability, "threshold": ml.threshold,
               "latency_ms": round(ml_ms, 2)},
        "ensemble": {"score": float(score), "threshold": 0.5},
        "reason": _reason(hres, ml),
    }


def _reason(hres: HeuristicResult, ml) -> str:
    parts = []
    if hres.blocked:
        parts.append("heurística (" + ", ".join(r["name"] for r in hres.matched_rules[:3]) + ")")
    if getattr(ml, "blocked", False):
        parts.append(f"ML (p={ml.probability:.2f})")
    return " + ".join(parts) or "permitido"