"""Reusable Plotly chart components (theme-aware)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dashboard.utils.theme import get_palette


def _pal() -> dict:
    return get_palette()


def apply_theme(fig: go.Figure, title: str | None = None, **layout_kw) -> go.Figure:
    """Apply the current dashboard theme (template + colors) to an existing figure."""
    pal = _pal()
    layout = dict(
        template=get_plotly_template(),
        paper_bgcolor=pal["card_bg"],
        plot_bgcolor=pal["card_bg"],
        font=dict(family="Segoe UI, Roboto, sans-serif", color=pal["text"]),
        hoverlabel=dict(bgcolor=pal["card_bg"], font=dict(color=pal["text"])),
        margin=dict(l=40, r=20, t=50, b=40),
    )
    if title is not None:
        layout["title"] = dict(text=title, x=0.5, xanchor="center")
    layout.update(layout_kw)
    fig.update_layout(**layout)
    fig.update_xaxes(gridcolor=pal["grid"])
    fig.update_yaxes(gridcolor=pal["grid"])
    return fig


def get_plotly_template() -> str:
    from dashboard.utils.theme import get_plotly_template as _tpl
    return _tpl()


def render_chart(fig: go.Figure, key: str | None = None) -> None:
    """Render a Plotly figure with the dashboard toolbar hidden, width stretch."""
    import streamlit as st
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": True}, key=key)


def _base(fig: go.Figure, title: str, x: str | None = None, y: str | None = None) -> go.Figure:
    apply_theme(fig, title)
    axes = {}
    if x:
        axes["xaxis_title"] = x
    if y:
        axes["yaxis_title"] = y
    fig.update_layout(**axes)
    return fig


def plot_asr_comparison(overall: dict) -> go.Figure:
    pal = _pal()
    without = overall.get("asr_without_filter", 0) * 100
    with_f = overall.get("asr_with_filter", 0) * 100
    fig = go.Figure(go.Bar(
        x=["ASR sin filtro", "ASR con filtro"],
        y=[without, with_f],
        marker_color=[pal["red"], pal["green"]],
        text=[f"{without:.1f}%", f"{with_f:.1f}%"],
        textposition="outside",
        hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
    ))
    fig.update_yaxes(title="ASR (%)", range=[0, max(without, with_f, 10) * 1.15])
    return _base(fig, "Attack Success Rate — antes y después del filtro")


def plot_confidence_distribution(df: pd.DataFrame, template: str | None = None) -> go.Figure:
    """Distribución de confianza del ensemble, bins adaptativos al tamaño de muestra."""
    pal = _pal()
    if df.empty or "ensemble_score" not in df.columns:
        return go.Figure()
    s = pd.to_numeric(df["ensemble_score"], errors="coerce").dropna()
    n = len(s)
    nbins = min(max(n // 2, 5), 30)
    data = pd.DataFrame({"score": s})
    fig = px.histogram(data, x="score", nbins=nbins, height=380,
                       color_discrete_sequence=[pal["primary"]],
                       labels={"score": "Score", "count": "Frecuencia"})
    if n < 30:
        fig.add_annotation(text=f"Muestra pequeña (n={n}): distribución poco representativa",
                           x=0.5, y=-0.15, xref="paper", yref="paper", showarrow=False,
                           font=dict(color=pal["text_faint"], size=11))
    return _base(fig, "Distribución de confianza del ensemble", x="Score", y="Frecuencia")


def plot_performance_by_dataset(rows: list[dict]) -> go.Figure:
    pal = _pal()
    if not rows:
        return go.Figure()
    names = [r["dataset"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="ASR sin filtro", x=names,
                         y=[r.get("asr_without_filter", 0) * 100 for r in rows],
                         marker_color=pal["red"]))
    fig.add_trace(go.Bar(name="ASR con filtro", x=names,
                         y=[r.get("asr_with_filter", 0) * 100 for r in rows],
                         marker_color=pal["green"]))
    fig.update_layout(barmode="group", legend=dict(orientation="h", y=-0.15))
    fig.update_yaxes(title="ASR (%)")
    return _base(fig, "Rendimiento por dataset")


def plot_performance_by_attack_type(df: pd.DataFrame) -> go.Figure:
    pal = _pal()
    at = df[df["label"].astype(int) == 1].copy()
    if at.empty:
        return go.Figure()
    det_rate = at.groupby("attack_type")["filter_blocked"].mean() * 100
    asr_ok = at.groupby("attack_type")["llm_success_with_filter"].mean().reindex(det_rate.index) * 100
    asr0 = at.groupby("attack_type")["llm_success_no_filter"].mean().reindex(det_rate.index) * 100
    names = det_rate.index.tolist()
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Tasa de bloqueo del filtro", x=names, y=det_rate.values, marker_color=pal["blue"]))
    fig.add_trace(go.Bar(name="ASR sin filtro", x=names, y=asr0.values, marker_color=pal["red"]))
    fig.add_trace(go.Bar(name="ASR con filtro", x=names, y=asr_ok.fillna(0).values, marker_color=pal["green"]))
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
    pal = _pal()
    fpr = roc.get("fpr", [0, 1])
    tpr = roc.get("tpr", [0, 1])
    auc = roc.get("auc")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name=f"AUC = {auc:.3f}" if auc else "curva ROC",
                             line=dict(color=pal["blue"], width=3)))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Azar",
                             line=dict(color="gray", dash="dash")))
    fig.update_layout(xaxis=dict(range=[0, 1.05]), yaxis=dict(range=[0, 1.05]),
                      xaxis_title="FPR", yaxis_title="TPR", legend=dict(orientation="h", y=-0.15))
    return _base(fig, "Curva ROC — capa ensemble")


def plot_latency_distribution(df: pd.DataFrame, col: str = "filter_latency_ms") -> go.Figure:
    pal = _pal()
    if df.empty or col not in df.columns:
        return go.Figure()
    s = pd.to_numeric(df[col], errors="coerce").dropna() * 1000  # ms
    fig = go.Figure(go.Histogram(x=s.values, nbinsx=30, marker_color=pal["blue"]))
    fig.update_layout(bargap=0.05)
    fig.update_xaxes(title="Latencia (ms)")
    fig.update_yaxes(title="Frecuencia")
    return _base(fig, "Distribución de latencia del filtro")


def plot_feature_importance(importances: list[dict], top: int = 20) -> go.Figure:
    pal = _pal()
    items = sorted(importances, key=lambda x: x["importance"], reverse=True)[:top]
    names = [it["dimension"] for it in items][::-1]
    vals = [it["importance"] for it in items][::-1]
    fig = go.Figure(go.Bar(x=vals, y=names, orientation="h", marker_color=pal["green"]))
    fig.update_layout(height=max(300, 24 * len(names)))
    fig.update_xaxes(title="Importancia")
    return _base(fig, f"Top {top} dimensiones más importantes (Random Forest)")


def plot_confidence_vs_correct(df: pd.DataFrame) -> go.Figure:
    pal = _pal()
    if df.empty or "ensemble_score" not in df.columns:
        return go.Figure()
    x = pd.to_numeric(df["ensemble_score"], errors="coerce")
    y = df["label"].astype(int)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x[y == 1], y=y[y == 1] + np.random.RandomState(1).uniform(-0.05, 0.05, int(y.sum())),
                             mode="markers", name="Maliciosos (correcto=bloqueo)",
                             marker=dict(color=pal["red"], opacity=0.7)))
    fig.add_trace(go.Scatter(x=x[y == 0], y=y[y == 0] + np.random.RandomState(2).uniform(-0.05, 0.05, int((y == 0).sum())),
                             mode="markers", name="Benignos (correcto=permitir)",
                             marker=dict(color=pal["green"], opacity=0.7)))
    fig.update_layout(yaxis=dict(tickmode="array", tickvals=[0, 1], ticktext=["Benigno", "Malicioso"]))
    fig.update_xaxes(title="Confianza del ensemble (score)")
    return _base(fig, "Confianza vs. clase real")


def plot_processing_by_layer(df: pd.DataFrame) -> go.Figure:
    pal = _pal()
    if df.empty or "heuristic_latency_ms" not in df.columns:
        return go.Figure()
    agg = df.groupby("dataset").agg(
        heur=("heuristic_latency_ms", "mean"),
        ml=("ml_latency_ms", "mean"),
    ) * 1000  # seconds -> ms
    agg = agg.sort_values("ml", ascending=False)
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Heurística", x=agg.index, y=agg["heur"], marker_color=pal["orange"]))
    fig.add_trace(go.Bar(name="ML (embeddings)", x=agg.index, y=agg["ml"], marker_color=pal["blue"]))
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

    pal = _pal()

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
        img = _wc(df[df["label"].astype(int) == 1], pal["card_bg"])
        if img:
            st.image(img, caption="Prompts maliciosos")
        else:
            st.info("Sin datos maliciosos")
    with c2:
        img = _wc(df[df["label"].astype(int) == 0], "#F8FAFC")
        if img:
            st.image(img, caption="Prompts benignos")
        else:
            st.info("Sin datos benignos")