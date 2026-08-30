"""Evaluate a trained classifier on a held-out test set.

Usage:
    python -m src.training.evaluate [--model models/random_forest.pkl]
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from src.filter.ml_filter import MLFilter
from src.training.dataset import load_training_data
from src.utils.config import load_config
from src.utils.logger import logger
from src.utils.visualizer import plot_confusion_matrix

_CONF = load_config()


def evaluate(model_path: str | None = None, threshold: float = 0.5) -> dict:
    df = load_training_data()
    y_true = df["label"].to_numpy(int)

    ml = MLFilter(model_path=model_path)
    probs = ml.predict_proba(df["prompt"].tolist())
    ml.threshold = threshold
    y_pred = (probs >= threshold).astype(int)

    cm = confusion_matrix(y_true, y_pred)
    report_df = pd.DataFrame(
        classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    ).transpose()

    plots_dir = Path(_CONF["paths"]["plots"])
    plot_confusion_matrix(cm, str(plots_dir / "evaluation_confusion_matrix.png"))
    report_df.to_csv(Path(_CONF["paths"]["results"]) / "model_evaluation_report.csv")
    logger.info("\n%s", classification_report(y_true, y_pred, zero_division=0))
    return {"cm": cm, "report": report_df}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    evaluate(model_path=args.model, threshold=args.threshold)