"""Página 5 — Attack Analysis: análisis detallado por tipo de ataque."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve()
while not (_ROOT / "src").exists() and _ROOT.parent != _ROOT:
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components import charts
from dashboard.components.metrics import section_header
from dashboard.utils.data_loader import load_benchmark_results

st.title("🎯 Attack Analysis — Análisis por tipo de ataque")

df = load_benchmark_results()
if df.empty:
    st.error("No hay resultados de benchmark. Ejecuta la evaluación primero.")
    st.stop()

datasets = sorted(df["dataset"].dropna().unique().tolist())
attack_types = sorted(df.loc[df["label"].astype(int) == 1, "attack_type"].dropna().unique().tolist())

with st.sidebar:
    st.markdown("### Filtros de análisis")
    ds_sel = st.multiselect("Dataset", datasets, default=datasets, key="aa_ds")
    at_sel = st.multiselect("Tipo de ataque", attack_types, default=attack_types, key="aa_at")

mask = df["dataset"].isin(ds_sel) & df["attack_type"].isin(at_sel) if at_sel else df["dataset"].isin(ds_sel)
sub = df[mask].copy()

# ------------------------------------------------------------ top payloads
section_header("Top payloads")
c1, c2 = st.columns(2)

attacks = sub[sub["label"].astype(int) == 1].copy()
with c1:
    st.subheader("😈 Top 10 — engañaron al filtro (falsos negativos)")
    sneaky = attacks[(attacks["filter_blocked"].astype(int) == 0)].sort_values("ensemble_score")
    if sneaky.empty:
        st.info("Ningún ataque logró superar el filtro en el conjunto seleccionado. 🎉")
    else:
        t = sneaky.head(10)[["prompt", "attack_type", "dataset", "ensemble_score", "heuristic_score"]]
        t = t.rename(columns={"prompt": "Prompt", "attack_type": "Tipo", "dataset": "Dataset",
                              "ensemble_score": "Score", "heuristic_score": "Heur."})
        st.dataframe(t.reset_index(drop=True), hide_index=True)

with c2:
    st.subheader("🔥 Top 10 — más peligrosos (engañaron al LLM)")
    p = attacks[(pd.to_numeric(attacks["llm_success_with_filter"], errors="coerce") == 1)]
    if p.empty:
        st.info("Ningún prompt seleccionado logró engañar al LLM.")
    else:
        t = p.sort_values("filter_latency_ms")[["prompt", "attack_type", "dataset", "ensemble_score"]]
        t = t.rename(columns={"prompt": "Prompt", "attack_type": "Tipo", "dataset": "Dataset",
                              "ensemble_score": "Score"})
        st.dataframe(t.reset_index(drop=True), hide_index=True)

# ------------------------------------------------------------ common patterns
section_header("Patrones comunes en ataques exitosos")
rules_col = sub["matched_rules"]
if pd.notna(rules_col).any():
    import collections
    counts = collections.Counter()
    for cell in rules_col.dropna():
        for r in str(cell).split(", "):
            if r:
                counts[r] += 1
    if counts:
        r_df = pd.DataFrame(counts.items(), columns=["Regla detectada", "Frecuencia"]).sort_values("Frecuencia", ascending=False)
        st.dataframe(r_df.head(15).reset_index(drop=True), hide_index=True)
    else:
        st.info("Sin reglas detectadas en el conjunto.")
else:
    st.info("Sin datos de reglas.")

# ------------------------------------------------------------ distributions
section_header("Distribuciones")
c1, c2 = st.columns(2)
with c1:
    sub2 = sub.copy()
    sub2["len"] = sub2["prompt"].str.len()
    fig = px.histogram(sub2, x="len", color="label", nbins=25,
                       color_discrete_map={1: "#DC2626", 0: "#16A34A"},
                       labels={"len": "Longitud (caracteres)", "count": "Prompts"})
    fig.update_layout(template="plotly_white", legend_title="Etiqueta",
                      title=dict(text="Longitud de prompts por categoría", x=0.5, xanchor="center"))
    st.plotly_chart(fig, width="stretch")

with c2:
    if "heuristic_score" in sub.columns:
        corr_cols = [c for c in ["heuristic_score", "ml_probability", "ensemble_score", "filter_latency_ms",
                                 "llm_success_with_filter"] if c in sub.columns]
        corr = sub[corr_cols].corr().round(2)
        fig = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                        title="Correlación entre características y éxito del ataque")
        st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------ word cloud
section_header("Word cloud de payloads")
with st.spinner("Generando nubes de palabras…"):
    charts.plot_word_cloud_side_by_side(df)