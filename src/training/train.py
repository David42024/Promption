"""Training the Random Forest classifier on embedding vectors.

Usage:
    python -m src.training.train [--embed-model all-MiniLM-L6-v2] [--out models/random_forest.pkl]
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from src.training.dataset import load_training_data
from src.utils.config import load_config
from src.utils.logger import logger
from src.utils.visualizer import plot_confusion_matrix, plot_feature_importance

_CONF = load_config()


def embed_dataset(df: pd.DataFrame, model_name: str, cache_path: Path | None = None) -> np.ndarray:
    if cache_path and cache_path.exists():
        cached = np.load(cache_path)
        if cached.shape[0] == len(df):
            logger.info("Loading cached embeddings from %s", cache_path)
            return cached
        logger.warning("Cached embeddings (%d filas) no coinciden con el dataset (%d). Recomputando.",
                       cached.shape[0], len(df))
        cache_path.unlink(missing_ok=True)

    logger.info("Computing embeddings with '%s' (%d texts)…", model_name, len(df))
    from sentence_transformers import SentenceTransformer
    encoder = SentenceTransformer(model_name)
    emb = encoder.encode(df["prompt"].tolist(), normalize_embeddings=True, batch_size=32, show_progress_bar=True)
    emb = np.asarray(emb, dtype=np.float32)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache_path, emb)
        logger.info("Embeddings cached to %s", cache_path)
    return emb


def main(embed_model: str | None = None, out_path: str | None = None, cache: bool = True) -> dict:
    df = load_training_data()
    y = df["label"].to_numpy(int)
    data_dir = Path(load_config()["paths"]["raw_data"]).parent
    cache_path = data_dir / "embeddings_train.npy"
    X = embed_dataset(
        df,
        embed_model or _CONF["model"]["embedding_model"],
        cache_path if cache else None,
    )

    # deterministic stratified split
    rng = np.random.RandomState(_CONF["model"].get("random_state", 42))
    perm = rng.permutation(len(df))
    split = int(len(df) * 0.8)
    tr_idx, te_idx = perm[:split], perm[split:]

    clf = RandomForestClassifier(
        n_estimators=int(_CONF["model"].get("n_trees", 200)),
        max_depth=int(_CONF["model"].get("max_depth", 20)),
        min_samples_leaf=int(_CONF["model"].get("min_samples_leaf", 2)),
        random_state=int(_CONF["model"].get("random_state", 42)),
        n_jobs=-1,
    )
    clf.fit(X[tr_idx], y[tr_idx])

    proba = clf.predict_proba(X[te_idx])
    pos_idx = int(np.flatnonzero(clf.classes_ == 1)[0])
    y_prob = proba[:, pos_idx]
    y_pred = clf.predict(X[te_idx])

    metrics = {
        "accuracy": float(accuracy_score(y[te_idx], y_pred)),
        "precision": float(precision_score(y[te_idx], y_pred, zero_division=0)),
        "recall": float(recall_score(y[te_idx], y_pred, zero_division=0)),
        "f1": float(f1_score(y[te_idx], y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y[te_idx], y_prob)),
        "n_samples": int(len(df)),
        "n_test": int(len(te_idx)),
        "n_features": int(X.shape[1]),
        "features": [f"dim_{i}" for i in range(X.shape[1])],
        "importances": [float(v) for v in clf.feature_importances_],
    }
    logger.info("Test metrics: %s", {k: v for k, v in metrics.items() if not isinstance(v, list)})

    model_dir = Path(out_path or _CONF["paths"]["classifier"]).parent
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = (Path(out_path).resolve() if out_path else Path(_CONF["paths"]["classifier"]))
    import joblib
    joblib.dump(clf, model_path)
    logger.info("Model saved to %s", model_path)

    plots_dir = Path(_CONF["paths"]["plots"])
    plot_confusion_matrix(confusion_matrix(y[te_idx], y_pred), str(plots_dir / "confusion_matrix.png"))
    plot_feature_importance(clf.feature_importances_, metrics["features"], str(plots_dir / "feature_importance.png"))

    # Persist evaluation as a CSV for the dashboard
    results_dir = Path(_CONF["paths"]["results"])
    pd.DataFrame([{k: v for k, v in metrics.items() if not isinstance(v, list)}]).to_csv(
        results_dir / "model_metrics.csv", index=False
    )
    logger.info("Evaluation metrics written to %s", results_dir / "model_metrics.csv")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed-model", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    main(embed_model=args.embed_model, out_path=args.out, cache=not args.no_cache)