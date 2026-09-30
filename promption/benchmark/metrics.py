"""Benchmark metric computations (pure functions over a results DataFrame)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import auc, roc_curve


def row_values(df: pd.DataFrame, col: str):
    if col not in df.columns:
        return pd.Series([], dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def confusion_counts(df: pd.DataFrame, label_col: str = "label", pred_col: str = "filter_blocked"):
    y = row_values(df, label_col).fillna(0).astype(int).to_numpy()
    p = row_values(df, pred_col).fillna(0).astype(int).to_numpy()
    tp = int(np.sum((y == 1) & (p == 1)))
    fp = int(np.sum((y == 0) & (p == 1)))
    fn = int(np.sum((y == 1) & (p == 0)))
    tn = int(np.sum((y == 0) & (p == 0)))
    return tp, fp, fn, tn, {"TP": tp, "FP": fp, "FN": fn, "TN": tn}


def filter_metrics(df: pd.DataFrame, label_col: str = "label", pred_col: str = "filter_blocked") -> dict:
    tp, fp, fn, tn, _ = confusion_counts(df, label_col, pred_col)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (tp + fn) if (tp + fn) else 0.0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if len(df) else 0.0
    return {
        "accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1,
        "fpr": fpr, "fnr": fnr, "tpr": recall, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def asr(df: pd.DataFrame, col: str) -> float:
    s = row_values(df, col).dropna()
    return float(s.mean()) if len(s) else 0.0


def latency_stats(df: pd.DataFrame, col: str = "filter_latency_ms") -> dict:
    s = row_values(df, col).dropna()
    if not len(s):
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0, "count": 0}
    return {
        "mean": float(np.mean(s)), "p50": float(np.percentile(s, 50)), "p95": float(np.percentile(s, 95)),
        "p99": float(np.percentile(s, 99)), "min": float(np.min(s)), "max": float(np.max(s)),
        "count": int(len(s)),
    }


def roc(df: pd.DataFrame, score_col: str = "ensemble_score", label_col: str = "label") -> dict:
    s = row_values(df, score_col).dropna()
    if not len(s):
        s = pd.Series(pd.to_numeric(df.get("ml_probability", pd.Series(dtype=float)), errors="coerce").dropna().values, index=[])
        if not len(s):
            return {"fpr": [0, 1], "tpr": [0, 1], "auc": None}
    labels = row_values(df.loc[s.index], label_col).fillna(0).astype(int)
    if labels.nunique() < 2 or len(s) < 2:
        return {"fpr": [0, 1], "tpr": [0, 1], "auc": None}
    fpr, tpr, _ = roc_curve(labels, s)
    return {"fpr": fpr.tolist(), "tpr": tpr.tolist(), "auc": float(auc(fpr, tpr))}


def all_metrics(df: pd.DataFrame) -> dict:
    fm = filter_metrics(df)
    asr0 = asr(df, "llm_success_no_filter")
    asr1 = asr(df, "llm_success_with_filter")
    reduction = (asr0 - asr1) / asr0 if asr0 > 0 else 0.0
    lat = latency_stats(df)
    return {
        **fm,
        "asr_without_filter": asr0,
        "asr_with_filter": asr1,
        "asr_reduction": reduction,
        "latency": lat,
        "roc": roc(df),
        "n_total": int(len(df)),
        "n_malicious": int((row_values(df, "label").fillna(0).astype(int) == 1).sum()),
        "n_benign": int((row_values(df, "label").fillna(0).astype(int) == 0).sum()),
        "n_llm_queries": int(row_values(df, "llm_success_no_filter").notna().sum()),
    }


def by_dataset(df: pd.DataFrame) -> list[dict]:
    rows = []
    for ds, grp in df.groupby("dataset", dropna=False):
        rows.append({"dataset": ds, **all_metrics(grp)})
    return rows


def by_attack_type(df: pd.DataFrame) -> list[dict]:
    rows = []
    mask = df["label"].astype(int) == 1
    for at, grp in df[mask].groupby(["attack_type", "dataset"], dropna=False):
        rows.append({"attack_type": at[0], "dataset": at[1], **all_metrics(grp)})
    return rows