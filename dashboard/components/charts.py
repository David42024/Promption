"""Reusable Plotly chart components."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dashboard.utils.theme import PALETTE

LAYOUT = dict(
    template="plotly_white",
    margin=dict(l=40, r=20, t=50, b=40),
    hoverlabel=dict(bgcolor="#1C1C28", font=dict(color="white")),
    font=dict(family="Segoe UI, Roboto, sans-serif"),
)


def _base(fig: go.Figure, title: str, x: str | None = None, y: str | None = None) -> go.Figure:
    fig.update_layout(**LAYOUT, title=dict(text=title, x=0.5, xanchor="center"))
    axes = {}
    if x:
        axes["xaxis_title"] = x
    if y:
        axes["yaxis_title"] = y
    fig.update_layout(**axes)
    return fig


def plot_asr_comparison(overall: dict) -> go.Figure:
    without = overall.get("asr_without_filter", 0) * 100
    with_f = overall.get("asr_with_filter", 0) * 100
    fig = go.Figure(go.Bar(
        x=["ASR sin filtro", "ASR con filtro"],
        y=[without, with_f],
        marker_color=[PALETTE["red"], PALETTE["green"]],
        text=[f"{without:.1f}%", f"{with_f:.1f}%"],
        textposition="outside",
        hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
    ))
    fig.update_yaxes(title="ASR (%)", range=[0, max(without, with_f, 10) * 1.15])
    return _base(fig, "Attack Success Rate — antes y después del filtro")


def plot_performance_by_dataset(rows: list[dict]) -> go.Figure:
    if not rows:
        return go.Figure()
    names = [r["dataset"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="ASR sin filtro", x=names,
                         y=[r.get("asr_without_filter", 0) * 100 for r in rows],
                         marker_color=PALETTE["red"]))
    fig.add_trace(go.Bar(name="ASR con filtro", x=names,
                         y=[r.get("asr_with_filter", 0) * 100 for r in rows],
                         marker_color=PALETTE["green"]))
    fig.update_layout(barmode="group", legend=dict(orientation="h", y=-0.15))
    fig.update_yaxes(title="ASR (%)")
    return _base(fig, "Rendimiento por dataset")


def plot_performance_by_attack_type(df: pd.DataFrame) -> go.Figure:
    at = df[df["label"].astype(int) == 1].copy()
    if at.empty:
        return go.Figure()
    det_rate = at.groupby("attack_type")["filter_blocked"].mean() * 100
    asr_ok = at.groupby("attack_type")["llm_success_with_filter"].mean().reindex(det_rate.index) * 100
    asr0 = at.groupby("attack_type")["llm_success_no_filter"].mean().reindex(det_rate.index) * 100
    names = det_rate.index.tolist()
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Tasa de bloqueo del filtro", x=names, y=det_rate.values, marker_color=PALETTE["blue"]))
    fig.add_trace(go.Bar(name="ASR sin filtro", x=names, y=asr0.values, marker_color=PALETTE["red"]))
    fig.add_trace(go.Bar(name="ASR con filtro", x=names, y=asr_ok.fillna(0).values, marker_color=PALETTE["green"]))
    fig.update_layout(barmode="group", legend=dict(orientation="h", y=-0.25))
    fig.update_yaxes(title="%")
    return _base(fig, "Detección y ASR por tipo de ataque")


def plot_confusion_matrix(tp: int, fp: int, fn: int, tn: int) -> go.Figure:
    z = [[tn, fp], [fn, tp]]
    labels = [["TN", "FP"], ["FN", "TP"]]
    text = [[f"{labels[i][j]}<br>{z[i][j]}<br>{v:.1f}%" for j, v in enumerate(row)]
            for i, row in enumerate((np.array(z) / max(np.sum(z), 1) * 100).tolist())]
    fig = go.Figure(go.Heatmap(
        z=np.array(z), x=["Permitido", "Bloqueado"], y=["Benigno", "Malicioso"],
        text=text, texttemplate="%{text}", colorscale="Blues", showscale=False,
        hovertemplate="Real: %{y}<br>Predicho: %{x}<br>Count: %{z}<extra></extra>",
    ))
    fig.update_layout(width=460, height=420)
    return _base(fig, "Matriz de confusión del filtro")


def plot_roc_curve(roc: dict) -> go.Figure:
    fpr = roc.get("fpr", [0, 1])
    tpr = roc.get("tpr", [0, 1])
    auc = roc.get("auc")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name=f"AUC = {auc:.3f}" if auc else "curva ROC",
                             line=dict(color=PALETTE["blue"], width=3)))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Azar",
                             line=dict(color="gray", dash="dash")))
    fig.update_layout(xaxis=dict(range=[0, 1.05]), yaxis=dict(range=[0, 1.05]),
                      xaxis_title="FPR", yaxis_title="TPR", legend=dict(orientation="h", y=-0.15))
    return _base(fig, "Curva ROC — capa ensemble")


def plot_latency_distribution(df: pd.DataFrame, col: str = "filter_latency_ms") -> go.Figure:
    if df.empty or col not in df.columns:
        return go.Figure()
    s = pd.to_numeric(df[col], errors="coerce").dropna() * 1000  # ms
    fig = go.Figure(go.Histogram(x=s.values, nbinsx=30, marker_color=PALETTE["blue"]))
    fig.update_layout(bargap=0.05)
    fig.update_xaxes(title="Latencia (ms)")
    fig.update_yaxes(title="Frecuencia")
    return _base(fig, "Distribución de latencia del filtro")


def plot_feature_importance(importances: list[dict], top: int = 20) -> go.Figure:
    items = sorted(importances, key=lambda x: x["importance"], reverse=True)[:top]
    names = [it["dimension"] for it in items][::-1]
    vals = [it["importance"] for it in items][::-1]
    fig = go.Figure(go.Bar(x=vals, y=names, orientation="h", marker_color=PALETTE["green"]))
    fig.update_layout(height=max(300, 24 * len(names)))
    fig.update_xaxes(title="Importancia")
    return _base(fig, f"Top {top} dimensiones más importantes (Random Forest)")


def plot_confidence_vs_correct(df: pd.DataFrame) -> go.Figure:
    if df.empty or "ensemble_score" not in df.columns:
        return go.Figure()
    x = pd.to_numeric(df["ensemble_score"], errors="coerce")
    y = df["label"].astype(int)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x[y == 1], y=y[y == 1] + np.random.RandomState(1).uniform(-0.05, 0.05, int(y.sum())),
                             mode="markers", name="Maliciosos (correcto=bloqueo)",
                             marker=dict(color=PALETTE["red"], opacity=0.7)))
    fig.add_trace(go.Scatter(x=x[y == 0], y=y[y == 0] + np.random.RandomState(2).uniform(-0.05, 0.05, int((y == 0).sum())),
                             mode="markers", name="Benignos (correcto=permitir)",
                             marker=dict(color=PALETTE["green"], opacity=0.7)))
    fig.update_layout(yaxis=dict(tickmode="array", tickvals=[0, 1], ticktext=["Benigno", "Malicioso"]))
    fig.update_xaxes(title="Confianza del ensemble (score)")
    return _base(fig, "Confianza vs. clase real")


def plot_processing_by_layer(df: pd.DataFrame) -> go.Figure:
    if df.empty or "heuristic_latency_ms" not in df.columns:
        return go.Figure()
    agg = df.groupby("dataset").agg(
        heur=("heuristic_latency_ms", "mean"),
        ml=("ml_latency_ms", "mean"),
    ) * 1000  # seconds -> ms
    agg = agg.sort_values("ml", ascending=False)
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Heurística", x=agg.index, y=agg["heur"], marker_color=PALETTE["orange"]))
    fig.add_trace(go.Bar(name="ML (embeddings)", x=agg.index, y=agg["ml"], marker_color=PALETTE["blue"]))
    fig.update_layout(barmode="stack", legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(title="Dataset")
    fig.update_yaxes(title="Tiempo medio (ms)")
    return _base(fig, "Tiempo de procesamiento por capa")


def plot_word_cloud_side_by_side(df: pd.DataFrame) -> None:
    """Two WordCloud images rendered side by side (imported lazily)."""
    global st, Image, WordCloud
    import streamlit as st
    from PIL import Image as PillowImage
    from wordcloud import WordCloud
    import io

    def _wc(sub, bg):
        txt = " ".join(sub["prompt"].astype(str).tolist())
        if not txt.strip():
            return None
        cloud = WordCloud(width=700, height=360, background_color=bg, max_words=80,
                          random_state=42, colormap="viridis").generate(txt)
        buf = io.BytesIO()
        cloud.to_image().save(buf, format="PNG")
        buf.seek(0)
        return PillowImage.open(buf)

    c1, c2 = st.columns(2)
    with c1:
        img = _wc(df[df["label"].astype(int) == 1], "black")
        if img:
            st.image(img, caption="Prompts maliciosos")
        else:
            st.info("Sin datos maliciosos")
    with c2:
        img = _wc(df[df["label"].astype(int) == 0], "white")
        if img:
            st.image(img, caption="Prompts benignos")
        else:
            st.info("Sin datos benignos")