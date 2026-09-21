"""Training a lightweight TF-IDF + Linear classifier for Render free.

Usage:
    python -m src.training.train_lightweight --out models/lightweight_classifier.pkl

This model is ~10-50MB and works on Render free (no SentenceTransformers).
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
import joblib

from src.training.dataset import load_training_data
from src.training.split import stratified_split
from src.utils.config import load_config
from src.utils.logger import logger

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
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pkl') as f:
        temp_path = Path(f.name)
        joblib.dump({'vectorizer': vectorizer, 'classifier': classifier}, temp_path)
        size_mb = temp_path.stat().st_size / (1024 * 1024)
        # No eliminar temporalmente para evitar error de permisos en Windows
    
    logger.info("Estimated model size: %.2f MB", size_mb)
    
    return {
        "accuracy": acc,
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "auc": auc,
        "size_mb": size_mb
    }


def main():
    parser = argparse.ArgumentParser(description="Train lightweight TF-IDF + LogisticRegression")
    parser.add_argument("--data", type=str, default=None, help="Path to training CSV")
    parser.add_argument("--max-features", type=int, default=10000, 
                       help="Max TF-IDF features (default: 10000)")
    parser.add_argument("--out", type=str, default="models/lightweight_classifier.pkl",
                       help="Output path for model")
    args = parser.parse_args()
    
    # Cargar datos
    df = load_training_data(args.data)
    logger.info("Loaded %d training samples", len(df))
    
    test_indices = stratified_split(
        df,
        seed=int(_CONF["model"].get("random_state", 42)),
    )
    test_set = set(test_indices.tolist())
    train_indices = np.array([index for index in range(len(df)) if index not in test_set])
    train_df = df.iloc[train_indices].reset_index(drop=True)
    test_df = df.iloc[test_indices].reset_index(drop=True)

    vectorizer, classifier, _ = train_lightweight_model(train_df, max_features=args.max_features)
    y_test = test_df["label"].to_numpy(int)
    metrics = evaluate_model(vectorizer, classifier, test_df, y_test)
    metrics["n_train"] = int(len(train_df))
    metrics["n_test"] = int(len(test_df))
    
    # Guardar modelo
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    model_data = {
        'vectorizer': vectorizer,
        'classifier': classifier,
        'metrics': metrics,
        'model_type': 'tfidf_logistic_regression',
        'max_features': args.max_features,
        'feature_mode': 'word_and_char_ngrams',
    }
    
    joblib.dump(model_data, out_path)
    logger.info("Model saved to %s", out_path)
    
    logger.info("\n✅ Lightweight model ready for Render free!")
    logger.info("   Estimated size: %.2f MB", metrics['size_mb'])
    logger.info("   Accuracy: %.2f%%", metrics['accuracy'] * 100)


if __name__ == "__main__":
    main()
