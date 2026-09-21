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
from src.filter.ensemble_filter import decide_pipeline_action, risk_band
from src.utils.config import load_embedding_model_name, load_classifier_path


class _MLNull:
    probability = None
    blocked = None


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
            from src.filter.ml_filter import chunk_text, prepare_texts
            enc, clf = load_ml_filter()
            tm0 = time.perf_counter()
            chunks = chunk_text(text)
            emb = np.asarray(enc.encode(prepare_texts(chunks), normalize_embeddings=True), dtype=np.float32)
            proba = clf.predict_proba(emb)[:, int(np.flatnonzero(clf.classes_ == 1)[0])]
            prob = float(proba.max())
            ml_ms = (time.perf_counter() - tm0) * 1000
            ml = type("ML", (), {"probability": prob, "blocked": prob > 0.66,
                                 "available": True})()
        except FileNotFoundError:
            ml = type("ML", (), {"probability": None, "blocked": None, "available": False})()
        except Exception:
            ml = type("ML", (), {"probability": None, "blocked": None, "available": False})()

    total_ms = (time.perf_counter() - t0) * 1000
    heuristic_risk = hres.score if hres.signal == "malicious" else 0.0
    explicit_benign_override = hres.signal == "benign"
    if ml.probability is None:
        score = heuristic_risk
    else:
        score = 0.4 * heuristic_risk + 0.6 * ml.probability
        if explicit_benign_override:
            score = 0.0
            ml.blocked = False
    decision = decide_pipeline_action(hres.score, ml.probability, 0.33, 0.66)
    blocked = decision == "BLOCKED"

    return {
        "text": text,
        "decision": decision,
        "blocked": bool(blocked),
        "confidence": float(score),
        "latency_ms": round(total_ms, 2),
        "sanitized": sanitize_prompt(text, hres) if blocked else text,
        "heuristic": {"blocked": hres.blocked, "score": hres.score, "signal": hres.signal,
                      "matched_rules": hres.matched_rules, "latency_ms": round(heur_ms, 2),
                      "benign_matched": list(hres.benign_matched)},
        "ml": {"available": ml.available if hasattr(ml, "available") else ml.probability is not None,
               "blocked": ml.blocked, "probability": ml.probability,
               "latency_ms": round(ml_ms, 2)},
        "ensemble": {"score": float(score),
                     "requires_output_guard": decision == "GUARDED",
                     "heuristic_band": risk_band(hres.score, 0.33, 0.66),
                     "ml_band": risk_band(ml.probability, 0.33, 0.66) if ml.probability is not None else "UNAVAILABLE",
                     "benign_matched": list(hres.benign_matched),
                     "explicit_benign_override": explicit_benign_override},
        "reason": _reason(hres, ml, decision),
    }


def _reason(hres: HeuristicResult, ml, decision: str) -> str:
    if decision == "GUARDED":
        probability = getattr(ml, "probability", None)
        value = "no disponible" if probability is None else f"{probability:.2f}"
        return f"requiere Output Guard (heurística={hres.score:.2f}, ML={value})"
    parts = []
    if hres.blocked:
        parts.append("heurística (" + ", ".join(r["name"] for r in hres.matched_rules[:3]) + ")")
    if getattr(ml, "blocked", False):
        parts.append(f"ML (p={ml.probability:.2f})")
    return " + ".join(parts) or "permitido"
