"""Deterministic, leakage-aware dataset splitting."""
import numpy as np
import pandas as pd


SYNTH_SOURCES = {
    "redteam_synth", "hard_negative", "translated_es", "translated_es2",
    "translated_gemini", "local", "synth_v2",
}


def stratified_split(df: pd.DataFrame, seed: int = 42, test_frac: float = 0.2) -> np.ndarray:
    """Return held-out indices stratified by label and language."""
    rng = np.random.RandomState(seed)
    parts = []
    public = (
        ~df["source"].astype(str).isin(SYNTH_SOURCES)
        if "source" in df.columns else pd.Series(True, index=df.index)
    )
    groups = df[public].groupby(["label", "lang"]).indices
    for _, indices in sorted(groups.items()):
        indices = np.asarray(indices)
        rng.shuffle(indices)
        count = max(1, int(len(indices) * test_frac)) if len(indices) > 1 else 1
        parts.append(indices[:count])
    return np.concatenate(parts) if parts else np.array([], dtype=int)
