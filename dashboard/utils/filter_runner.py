"""Dashboard adapter for the same configured ensemble used by the API and benchmark."""
import streamlit as st

from promption.benchmark.runner import sanitize_prompt
from promption.filter.ensemble_filter import EnsembleFilter


@st.cache_resource(show_spinner="Cargando filtro configurado…")
def load_filter():
    return EnsembleFilter()


def filter_text(text: str, use_ml: bool = True):
    """Return display data without duplicating model selection or security decisions."""
    result = load_filter().analyze(text, use_ml=use_ml)
    heuristic = result.heuristic
    ml = result.ml
    return {
        "text": text,
        "decision": result.decision,
        "blocked": result.blocked,
        "confidence": result.score,
        "latency_ms": round(result.latency_ms, 2),
        "sanitized": sanitize_prompt(text, result) if result.blocked else text,
        "heuristic": {
            "blocked": heuristic.blocked, "score": heuristic.score, "signal": heuristic.signal,
            "matched_rules": heuristic.matched_rules, "benign_matched": list(heuristic.benign_matched),
            "latency_ms": round(result.heuristic_latency_ms, 2),
        },
        "ml": {
            "available": ml is not None, "blocked": ml.blocked if ml else None,
            "probability": ml.probability if ml else None,
            "latency_ms": round(result.ml_latency_ms, 2),
        },
        "ensemble": {**result.merged_features, "score": result.score},
        "reason": result.blocking_reason,
    }
