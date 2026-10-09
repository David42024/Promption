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
    raw_without = overall.get("asr_without_filter")
    raw_with = overall.get("asr_with_filter")

    if raw_without is None and raw_with is None:
        fig = go.Figure()
        fig.add_annotation(
            text="ASR no evaluado (sin ataques o LLM no consultado)",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=pal["text_faint"], size=13),
        )
        return _base(fig, "Attack Success Rate — antes y después del filtro")

    without = raw_without * 100 if raw_without is not None else None
    with_f = raw_with * 100 if raw_with is not None else None
    text_without = f"{without:.1f}%" if without is not None else "N/A"
    text_with = f"{with_f:.1f}%" if with_f is not None else "N/A"

    fig = go.Figure(go.Bar(
        x=["ASR amplio sin filtro", "ASR amplio protegido"],
        y=[without, with_f],
        marker_color=[pal["red"], pal["green"]],
        text=[text_without, text_with],
        textposition="outside",
        hovertemplate="%{x}: %{text}<extra></extra>",
    ))
    valid_vals = [v for v in [without, with_f] if v is not None]
    max_val = max(valid_vals) if valid_vals else 10
    fig.update_yaxes(title="ASR (%)", range=[0, max(max_val, 10) * 1.15])
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
    y_without = [r.get("asr_without_filter") * 100 if r.get("asr_without_filter") is not None else None for r in rows]
    y_with = [r.get("asr_with_filter") * 100 if r.get("asr_with_filter") is not None else None for r in rows]
    text_without = [f"{v:.1f}%" if v is not None else "N/A" for v in y_without]
    text_with = [f"{v:.1f}%" if v is not None else "N/A" for v in y_with]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="ASR amplio sin filtro", x=names,
                         y=y_without, text=text_without, textposition="outside",
                         marker_color=pal["red"]))
    fig.add_trace(go.Bar(name="ASR amplio protegido", x=names,
                         y=y_with, text=text_with, textposition="outside",
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
    y_asr0 = [v if pd.notna(v) else None for v in asr0.values]
    y_asr_ok = [v if pd.notna(v) else None for v in asr_ok.values]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Tasa de bloqueo del filtro", x=names, y=det_rate.values, marker_color=pal["blue"]))
    fig.add_trace(go.Bar(name="ASR amplio sin filtro", x=names, y=y_asr0, marker_color=pal["red"]))
    fig.add_trace(go.Bar(name="ASR amplio protegido", x=names, y=y_asr_ok, marker_color=pal["green"]))
    fig.update_layout(barmode="group", legend=dict(orientation="h", y=-0.25))
    fig.update_yaxes(title="%")
    return _base(fig, "Detección y ASR por tipo de ataque")


def plot_confusion_matrix(tp: int, fp: int, fn: int, tn: int, title: str = "Matriz de confusión del filtro") -> go.Figure:
    z = [[tn, fp], [fn, tp]]
    labels = [["TN", "FP"], ["FN", "TP"]]
    total = max(int(np.sum(z)), 1)
    text = [[f"{labels[i][j]}<br>{z[i][j]}<br>{v:.1f}%" for j, v in enumerate(row)]
            for i, row in enumerate((np.array(z) / total * 100).tolist())]
    fig = go.Figure(go.Heatmap(
        z=np.array(z), x=["Permitido", "Bloqueado"], y=["Benigno", "Malicioso"],
        text=text, texttemplate="%{text}", colorscale="Blues", showscale=False,
        hovertemplate="Real: %{y}<br>Predicho: %{x}<br>Count: %{z}<extra></extra>",
    ))
    fig.update_layout(width=460, height=420)
    return _base(fig, title)


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


def plot_layer_blocks(df: pd.DataFrame) -> go.Figure:
    """Bloqueos desglosados por capa: heurística, ML, alcance/permisos y output guard."""
    pal = _pal()
    if df.empty:
        return go.Figure()
    
    heur_blocks = int(pd.to_numeric(df.get("heuristic_blocked", 0), errors="coerce").fillna(0).sum())
    ml_blocks = int(pd.to_numeric(df.get("ml_blocked", 0), errors="coerce").fillna(0).sum()) if "ml_blocked" in df.columns else 0
    scope_blocks = int((df.get("scope_decision") == "BLOCKED").sum()) if "scope_decision" in df.columns else 0
    guard_blocks = int((df.get("output_guard_action") == "BLOCK").sum()) if "output_guard_action" in df.columns else 0
    guard_redacts = int((df.get("output_guard_action") == "REDACT").sum()) if "output_guard_action" in df.columns else 0
    
    names = ["Heurística", "ML", "Alcance/Permisos", "Output Guard (Bloqueo)", "Output Guard (Redacción)"]
    vals = [heur_blocks, ml_blocks, scope_blocks, guard_blocks, guard_redacts]
    colors = [pal["orange"], pal["blue"], pal["purple"] if "purple" in pal else pal["primary"], pal["red"], pal["green"]]
    
    fig = go.Figure(go.Bar(
        x=names, y=vals, text=[str(v) for v in vals], textposition="outside",
        marker_color=colors,
    ))
    fig.update_layout(yaxis_title="Cantidad de intervenciones", showlegend=False)
    return _base(fig, "Intervenciones y bloqueos por capa")


def plot_leaks_before_after(df: pd.DataFrame) -> go.Figure:
    """Comparativa de fugas estrictas del secreto antes y después de Output Guard."""
    pal = _pal()
    if df.empty or "secret_leaked_before_guard" not in df.columns:
        return go.Figure()
    
    mal = df[pd.to_numeric(df.get("label", 0), errors="coerce").fillna(0).astype(int) == 1]
    s_before = pd.to_numeric(mal.get("secret_leaked_before_guard", pd.Series(dtype=float)), errors="coerce").dropna()
    s_after = pd.to_numeric(mal.get("secret_leaked_after_guard", pd.Series(dtype=float)), errors="coerce").dropna()
    
    leaks_before = int((s_before == 1.0).sum())
    leaks_after = int((s_after == 1.0).sum())
    prevented = max(0, leaks_before - leaks_after)
    
    names = ["Fugas antes de Output Guard", "Fugas entregadas tras Guard", "Fugas prevenidas / neutralizadas"]
    vals = [leaks_before, leaks_after, prevented]
    colors = [pal["red"], pal["red"] if leaks_after > 0 else pal["green"], pal["green"]]
    
    fig = go.Figure(go.Bar(
        x=names, y=vals, text=[str(v) for v in vals], textposition="outside",
        marker_color=colors,
    ))
    fig.update_layout(yaxis_title="Casos", showlegend=False)
    return _base(fig, "Confidencialidad: Fugas de secreto antes y después de Output Guard")


def plot_latency_breakdown(df: pd.DataFrame) -> go.Figure:
    """Distribución de latencias medias por capa del recorrido."""
    pal = _pal()
    if df.empty:
        return go.Figure()
    
    heur_mean = float(pd.to_numeric(df.get("heuristic_latency_ms", pd.Series(dtype=float)), errors="coerce").dropna().mean() or 0.0)
    ml_mean = float(pd.to_numeric(df.get("ml_latency_ms", pd.Series(dtype=float)), errors="coerce").dropna().mean() or 0.0)
    scope_mean = float(pd.to_numeric(df.get("scope_latency_ms", pd.Series(dtype=float)), errors="coerce").dropna().mean() or 0.0)
    og_mean = float(pd.to_numeric(df.get("output_guard_latency_ms", pd.Series(dtype=float)), errors="coerce").dropna().mean() or 0.0)

    # Avoid mixing fast early blocks or non-executed calls into LLM generation latency
    llm_series = pd.to_numeric(df.get("generation_latency_ms", pd.Series(dtype=float)), errors="coerce").dropna()
    if llm_series.empty:
        if "generation_executed" in df.columns:
            gen_mask = pd.to_numeric(df["generation_executed"], errors="coerce").fillna(0).astype(int) == 1
            llm_series = pd.to_numeric(df.loc[gen_mask, "llm_latency_ms"], errors="coerce").dropna()
        else:
            llm_series = pd.to_numeric(df.get("llm_latency_ms", pd.Series(dtype=float)), errors="coerce").dropna()
    llm_mean = float(llm_series.mean() or 0.0)
    
    names = ["Heurística", "ML", "Alcance", "Output Guard", "Generación LLM"]
    vals = [round(heur_mean, 2), round(ml_mean, 2), round(scope_mean, 2), round(og_mean, 2), round(llm_mean, 2)]
    
    fig = go.Figure(go.Bar(
        x=names, y=vals, text=[f"{v} ms" for v in vals], textposition="outside",
        marker_color=[pal["orange"], pal["blue"], pal["primary"], pal["green"], pal["red"]],
    ))
    fig.update_layout(yaxis_title="Latencia media (ms)", showlegend=False)
    return _base(fig, "Latencia media por etapa del sistema")
