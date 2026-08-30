"""Static visualization helpers (matplotlib / seaborn).

These produce PNG reports used by ``scripts/run_benchmark.py`` and
``scripts/generate_report.py``. The interactive Streamlit dashboard uses its
own Plotly-based charts (see ``dashboard/components/charts.py``).
"""
import matplotlib

matplotlib.use("Agg")  # headless backend

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.utils.logger import logger

sns.set_theme(style="whitegrid")
FIGSIZE = (9, 5)


def plot_asr_comparison(asr_without: float, asr_with: float, save_path: str) -> None:
    fig, ax = plt.subplots(figsize=FIGSIZE)
    bars = ax.bar(["Sin filtro", "Con filtro"], [asr_without * 100, asr_with * 100],
                  color=["#d62728", "#2ca02c"])
    for b in bars:
        ax.annotate(f"{b.get_height():.1f}%", (b.get_x() + b.get_width() / 2, b.get_height() + 1),
                    ha="center", fontweight="bold")
    ax.set_ylabel("ASR (%)")
    ax.set_ylim(0, max(asr_without, asr_with) * 100 * 1.15 + 5)
    ax.set_title("Attack Success Rate: sin vs con filtro")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def plot_performance_by_attack(df: pd.DataFrame, save_path: str) -> None:
    """Bar plot of ASR and detection rate grouped by attack type."""
    df = df[df.get("dataset").notna()] if "dataset" in df else df
    grouped = df.groupby(list({"dataset"} & set(df.columns)))
    rows = []
    for name, grp in grouped:
        rows.append({
            "dataset": name,
            "asr_without": grp.get("asr_without", pd.Series([np.nan])).mean(),
            "asr_with": grp.get("asr_with", pd.Series([np.nan])).mean(),
            "attack_count": len(grp),
        })
    if not rows:
        logger.warning("No data for performance-by-attack plot")
        return
    plot_df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    x = np.arange(len(plot_df))
    width = 0.35
    ax.bar(x - width / 2, plot_df["asr_without"] * 100, width, label="ASR sin filtro", color="#d62728")
    ax.bar(x + width / 2, plot_df["asr_with"] * 100, width, label="ASR con filtro", color="#2ca02c")
    ax.set_xticks(x)
    ax.set_xticklabels(plot_df["dataset"], rotation=30, ha="right")
    ax.set_ylabel("ASR (%)")
    ax.legend()
    ax.set_title("Rendimiento por tipo de ataque")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def plot_latency_distribution(latencies: list[float], save_path: str) -> None:
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.hist(np.asarray(latencies, dtype=float) * 1000, bins=30, color="#1f77b4", edgecolor="white")
    ax.set_xlabel("Latencia (ms)")
    ax.set_ylabel("Frecuencia")
    ax.set_title("Distribución de latencia del filtro")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def plot_confusion_matrix(cm: np.ndarray, save_path: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=["Permitido", "Bloqueado"],
                yticklabels=["Permitido", "Bloqueado"], ax=ax)
    ax.set_xlabel("Predicción")
    ax.set_ylabel("Real")
    ax.set_title("Matriz de confusión del filtro")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def plot_feature_importance(importances: list[float], feature_names: list[str], save_path: str) -> None:
    order = np.argsort(importances)[::-1][:20]
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.barh([feature_names[i] for i in order][::-1], [importances[i] for i in order][::-1], color="#7f7f7f")
    ax.set_xlabel("Importancia")
    ax.set_title("Feature importance del Random Forest")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)