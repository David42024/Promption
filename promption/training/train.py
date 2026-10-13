"""Training the Random Forest classifier on embedding vectors.

Usage:
    python -m promption.training.train [--embed-model all-MiniLM-L6-v2] [--out models/random_forest.pkl]
"""
import argparse
import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from datetime import datetime, timezone
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

from promption.training.dataset import load_training_data
from promption.training.split import SYNTH_SOURCES, create_splits, save_manifest
from promption.training.artifacts import file_sha256, preserve_records
from promption.utils.config import load_config
from promption.utils.logger import logger

_CONF = load_config()


def encoder_runtime_versions() -> dict:
    """Record optional encoder runtime packages without requiring them in mocked tests."""
    result = {}
    for package in ("torch", "sentence-transformers", "transformers"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None
    return result


def embedding_fingerprint(df: pd.DataFrame, model_name: str, prefix: str, revision: str | None = None) -> str:
    """Identify ordered texts and the complete frozen-encoder preprocessing contract."""
    content = {"model": model_name, "revision": revision, "prefix": prefix, "normalize_embeddings": True,
               "prompts": df["prompt"].astype(str).tolist()}
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode("utf-8")).hexdigest()


def embed_dataset(df: pd.DataFrame, model_name: str, cache_path: Path | None = None) -> np.ndarray:
    model_config = load_config()["model"]
    prefix = str(model_config.get("embedding_prefix", "") or "")
    revision = model_config.get("embedding_revision")
    fingerprint = embedding_fingerprint(df, model_name, prefix, revision)
    meta_path = cache_path.with_suffix(".metadata.json") if cache_path else None
    if cache_path and cache_path.exists() and meta_path.is_file():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            cached = np.load(cache_path, allow_pickle=False)
            if (metadata.get("fingerprint") == fingerprint and cached.ndim == 2
                    and cached.shape == (len(df), metadata.get("dimensions"))
                    and np.isfinite(cached).all()):
                logger.info("Loading verified cached embeddings from %s", cache_path)
                return cached
        except (ValueError, OSError, TypeError):
            logger.warning("Invalid embedding cache; recomputing")

    logger.info("Computing embeddings with '%s' (%d texts)…", model_name, len(df))
    from sentence_transformers import SentenceTransformer
    encoder = SentenceTransformer(model_name, **({"revision": revision} if revision else {}))
    emb = encoder.encode([prefix + str(t) for t in df["prompt"]], normalize_embeddings=True,
                         batch_size=32, show_progress_bar=True)
    emb = np.asarray(emb, dtype=np.float32)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache_path, emb)
        meta_path.write_text(json.dumps({"fingerprint": fingerprint,
                                        "dimensions": int(emb.shape[1])}), encoding="utf-8")
        logger.info("Embeddings cached to %s", cache_path)
    return emb


# Filas de aumento sintético: pertenecen a familias creadas para enseñar y
# NUNCA deben caer en test (una familia no se reparte entre train y test).
# El benchmark externo (data/eval/redteam_100.csv) jamás entra a train.
def slice_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> dict:
    from sklearn.metrics import precision_recall_fscore_support
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {"accuracy": float(accuracy_score(y_true, y_pred)), "precision": float(p),
            "recall": float(r), "f1": float(f)}


def main(embed_model: str | None = None, out_path: str | None = None,
         cache: bool = True, preserve: bool = True,
         data_path: str | Path | None = None) -> dict:
    from promption.utils.visualizer import plot_confusion_matrix, plot_feature_importance

    df = pd.read_csv(data_path, encoding="utf-8") if data_path else load_training_data()
    y = df["label"].to_numpy(int)
    data_dir = Path(load_config()["paths"]["raw_data"]).parent
    encoder_name = embed_model or _CONF["model"]["embedding_model"]
    prefix = str(_CONF["model"].get("embedding_prefix", "") or "")
    cache_key = embedding_fingerprint(df, encoder_name, prefix, _CONF["model"].get("embedding_revision"))
    cache_path = data_dir / f"embeddings_train_{cache_key[:16]}.npy"
    X = embed_dataset(
        df,
        encoder_name,
        cache_path if cache else None,
    )

    seed = int(_CONF["model"].get("random_state", 42))
    tr_idx, v_idx, te_idx, ext_idx = create_splits(df, seed=seed)

    out_dir = Path(_CONF["paths"]["processed_data"])
    manifest = save_manifest(df, tr_idx, v_idx, te_idx, ext_idx, seed=seed, out_dir=out_dir)

    clf = RandomForestClassifier(
        n_estimators=int(_CONF["model"].get("n_trees", 200)),
        max_depth=int(_CONF["model"].get("max_depth", 20)),
        min_samples_leaf=int(_CONF["model"].get("min_samples_leaf", 2)),
        max_features=_CONF["model"].get("max_features", "sqrt"),
        class_weight=_CONF["model"].get("class_weight"),
        random_state=int(_CONF["model"].get("random_state", 42)),
        n_jobs=-1,
    )
    clf.fit(X[tr_idx], y[tr_idx])

    pos_idx = int(np.flatnonzero(clf.classes_ == 1)[0])
    threshold = float(_CONF.get("ensemble", {}).get("decision_high_threshold", 0.66))

    # Evaluación en partición de validación
    val_proba = clf.predict_proba(X[v_idx])[:, pos_idx]
    val_pred = (val_proba >= threshold).astype(int)
    val_metrics = {
        "accuracy": float(accuracy_score(y[v_idx], val_pred)),
        "precision": float(precision_score(y[v_idx], val_pred, zero_division=0)),
        "recall": float(recall_score(y[v_idx], val_pred, zero_division=0)),
        "f1": float(f1_score(y[v_idx], val_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y[v_idx], val_proba)),
        "n_val": int(len(v_idx)),
        "decision_threshold": threshold,
        "false_positive_rate": float(np.mean(val_pred[y[v_idx] == 0])),
    }

    # Evaluación en partición de test
    proba = clf.predict_proba(X[te_idx])
    y_prob = proba[:, pos_idx]
    y_pred = (y_prob >= threshold).astype(int)

    metrics = {
        "accuracy": float(accuracy_score(y[te_idx], y_pred)),
        "precision": float(precision_score(y[te_idx], y_pred, zero_division=0)),
        "recall": float(recall_score(y[te_idx], y_pred, zero_division=0)),
        "f1": float(f1_score(y[te_idx], y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y[te_idx], y_prob)),
        "n_samples": int(len(df)),
        "n_train": int(len(tr_idx)),
        "n_val": int(len(v_idx)),
        "n_test": int(len(te_idx)),
        "n_features": int(X.shape[1]),
        "decision_threshold": threshold,
        "false_positive_rate": float(np.mean(y_pred[y[te_idx] == 0])),
        "features": [f"dim_{i}" for i in range(X.shape[1])],
        "importances": [float(v) for v in clf.feature_importances_],
    }
    for lang in ("en", "es"):
        mask = (df["lang"].to_numpy()[te_idx] == lang)
        metrics[f"n_test_{lang}"] = int(mask.sum())
        if mask.sum() >= 2 and len(set(y[te_idx][mask])) > 1:
            for k, v in slice_metrics(y[te_idx][mask], y_pred[mask], y_prob[mask]).items():
                metrics[f"{k}_{lang}"] = v
    logger.info("Test metrics: %s", {k: v for k, v in metrics.items() if not isinstance(v, list)})

    model_dir = Path(out_path or _CONF["paths"]["classifier"]).parent
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = (Path(out_path).resolve() if out_path else Path(_CONF["paths"]["classifier"]))
    if preserve:
        preserve_records()
    import joblib
    joblib.dump(clf, model_path)
    import sklearn
    model_path.with_suffix(".metadata.json").write_text(json.dumps({
        "backend": "embeddings_random_forest",
        "sha256": file_sha256(model_path),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest(),
        "manifest_hash": manifest.get("hash"),
        "manifest_splits": manifest.get("splits"),
        "embedding_model": embed_model or _CONF["model"]["embedding_model"],
        "sklearn_version": sklearn.__version__,
        "seed": int(_CONF["model"].get("random_state", 42)),
        "classifier_parameters": clf.get_params(),
        "metrics": {key: value for key, value in metrics.items() if not isinstance(value, list)},
        "val_metrics": val_metrics,
        "embedding_prefix": prefix,
        "embedding_revision": _CONF["model"].get("embedding_revision"),
        "encoder_runtime_versions": encoder_runtime_versions(),
        "embedding_cache_fingerprint": cache_key,
        "training_distribution": df.iloc[tr_idx].groupby(["lang", "label"]).size()
            .reset_index(name="count").to_dict(orient="records"),
        "augmentation_source": "spanish_curated_train_v1" if
            df.iloc[tr_idx]["source"].eq("spanish_curated_train_v1").any() else None,
    }, indent=2), encoding="utf-8")
    logger.info("Model saved to %s", model_path)

    plots_dir = Path(_CONF["paths"]["plots"])
    plot_confusion_matrix(confusion_matrix(y[te_idx], y_pred), str(plots_dir / "confusion_matrix.png"))
    plot_feature_importance(clf.feature_importances_, metrics["features"], str(plots_dir / "feature_importance.png"))

    # Persist evaluation as a CSV for the dashboard
    results_dir = Path(_CONF["paths"]["results"])
    results_dir.mkdir(parents=True, exist_ok=True)
    metrics["backend"] = "embeddings_random_forest"
    metrics_frame = pd.DataFrame([{k: v for k, v in metrics.items() if not isinstance(v, list)}])
    metrics_frame.to_csv(results_dir / "model_metrics_embeddings_random_forest.csv", index=False)
    if not _CONF["model"].get("use_lightweight_ml", False):
        metrics_frame.to_csv(results_dir / "model_metrics.csv", index=False)
    logger.info("Evaluation metrics written to %s", results_dir / "model_metrics_embeddings_random_forest.csv")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed-model", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    main(embed_model=args.embed_model, out_path=args.out, cache=not args.no_cache)
