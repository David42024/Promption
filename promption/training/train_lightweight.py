"""Training a lightweight TF-IDF + Linear classifier for Render free.

Usage:
    python -m promption.training.train_lightweight --out models/lightweight_classifier.pkl

This backend runs without SentenceTransformers.
"""
import argparse
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
import joblib

from promption.training.dataset import load_training_data
from promption.training.split import stratified_split
from promption.training.artifacts import file_sha256, preserve_records
from promption.utils.config import load_config
from promption.utils.logger import logger

_CONF = load_config()


def train_lightweight_model(df: pd.DataFrame, max_features: int = 10000) -> tuple:
    """Train TF-IDF + LogisticRegression (very lightweight)."""
    logger.info("Training lightweight TF-IDF + LogisticRegression model...")
    
    # Limpiar datos: eliminar filas con labels NaN
    df = df.dropna(subset=['label', 'prompt'])
    
    # Mapear labels a 0/1 (manejar ambos formatos: texto y numérico)
    if df['label'].dtype == object:
        y = df["label"].map({"injection": 1, "benign": 0, 1: 1, 0: 0}).values
    else:
        y = df["label"].values
    
    # Eliminar filas con labels inválidos
    valid_mask = ~np.isnan(y)
    df = df[valid_mask]
    y = y[valid_mask]
    
    logger.info("Cleaned training samples: %d", len(df))
    
    # Configurar TF-IDF con límites para mantener el modelo pequeño
    vectorizer = FeatureUnion([
        ("word", TfidfVectorizer(
            max_features=max_features,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            lowercase=True,
            sublinear_tf=True,
        )),
        ("char", TfidfVectorizer(
            analyzer="char_wb",
            max_features=max_features,
            ngram_range=(3, 5),
            min_df=2,
            lowercase=True,
            sublinear_tf=True,
        )),
    ])
    
    X = vectorizer.fit_transform(df["prompt"].tolist())
    
    logger.info("TF-IDF features: %d", X.shape[1])
    logger.info("Training samples: %d (injection: %d, benign: %d)", 
                len(y), np.sum(y), np.sum(y == 0))
    
    # LogisticRegression es muy ligero y rápido
    classifier = LogisticRegression(
        max_iter=1000,
        C=1.0,
        class_weight='balanced',
        random_state=42
    )
    
    classifier.fit(X, y)
    
    return vectorizer, classifier, y


def evaluate_model(vectorizer, classifier, df: pd.DataFrame, y_true):
    """Evaluate the lightweight model."""
    X_test = vectorizer.transform(df["prompt"].tolist())
    
    y_pred = classifier.predict(X_test)
    y_proba = classifier.predict_proba(X_test)[:, 1]
    
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred)
    recall = recall_score(y_true, y_pred)
    
    try:
        auc = roc_auc_score(y_true, y_proba)
    except:
        auc = 0.5
    
    logger.info("=" * 60)
    logger.info("Lightweight Model Evaluation")
    logger.info("=" * 60)
    logger.info("Accuracy: %.4f", acc)
    logger.info("F1 Score: %.4f", f1)
    logger.info("Precision: %.4f", precision)
    logger.info("Recall: %.4f", recall)
    logger.info("ROC AUC: %.4f", auc)
    logger.info("=" * 60)
    logger.info("\nClassification Report:\n%s", classification_report(y_true, y_pred))
    logger.info("=" * 60)
    
    # Estimar tamaño del modelo en disco
    buffer = io.BytesIO()
    joblib.dump({'vectorizer': vectorizer, 'classifier': classifier}, buffer)
    size_mb = buffer.tell() / (1024 * 1024)
    
    logger.info("Estimated model size: %.2f MB", size_mb)
    
    return {
        "accuracy": acc,
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "auc": auc,
        "size_mb": size_mb
    }


def train(data_path: str | None = None, out_path: str | Path | None = None,
          max_features: int = 10000, *, preserve: bool = True) -> dict:
    """Train the same lightweight artifact loaded by the configured ensemble."""
    if preserve:
        preserve_records()
    if data_path is None:
        df = load_training_data()
    else:
        df = pd.read_csv(data_path)
        if "lang" not in df.columns:
            from promption.utils.lang import detect_lang
            df["lang"] = df["prompt"].map(detect_lang)
    logger.info("Loaded %d training samples", len(df))
    test_indices = stratified_split(df, seed=int(_CONF["model"].get("random_state", 42)))
    test_set = set(test_indices.tolist())
    train_indices = np.array([index for index in range(len(df)) if index not in test_set])
    train_df = df.iloc[train_indices].reset_index(drop=True)
    test_df = df.iloc[test_indices].reset_index(drop=True)
    if train_df["label"].nunique() != 2 or test_df["label"].nunique() != 2:
        raise ValueError("Training and evaluation partitions must both contain benign and malicious samples")
    vectorizer, classifier, _ = train_lightweight_model(train_df, max_features=max_features)
    metrics = evaluate_model(vectorizer, classifier, test_df, test_df["label"].to_numpy(int))
    metrics.update(n_train=len(train_df), n_test=len(test_df), n_samples=len(df),
                   n_features=len(vectorizer.get_feature_names_out()),
                   backend="tfidf_logistic_regression", roc_auc=metrics["auc"])
    target = Path(out_path or _CONF["model"]["lightweight_classifier_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'vectorizer': vectorizer, 'classifier': classifier, 'metrics': metrics,
                 'model_type': 'tfidf_logistic_regression', 'max_features': max_features,
                 'feature_mode': 'word_and_char_ngrams'}, target)
    import sklearn
    import hashlib
    dataset_hash = hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()
    metadata = {"backend": metrics["backend"], "sha256": file_sha256(target),
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "dataset_sha256": dataset_hash, "sklearn_version": sklearn.__version__,
                "seed": int(_CONF["model"].get("random_state", 42)), "metrics": metrics}
    target.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    results = Path(_CONF["paths"]["results"])
    results.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([metrics]).to_csv(results / "model_metrics_tfidf.csv", index=False)
    if _CONF["model"].get("use_lightweight_ml", False):
        pd.DataFrame([metrics]).to_csv(results / "model_metrics.csv", index=False)
    logger.info("TF-IDF model saved: %s (sha256=%s)", target, metadata["sha256"])
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Train lightweight TF-IDF + LogisticRegression")
    parser.add_argument("--data", type=str, default=None, help="Path to training CSV")
    parser.add_argument("--max-features", type=int, default=10000, 
                       help="Max TF-IDF features (default: 10000)")
    parser.add_argument("--out", type=str, default=None,
                       help="Output path for model")
    args = parser.parse_args()
    
    train(args.data, args.out, args.max_features)


if __name__ == "__main__":
    main()
