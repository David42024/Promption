"""Página 2 — Benchmark Results: análisis detallado."""
import pandas as pd
import streamlit as st

from dashboard.components import charts
from dashboard.components.metrics import section_header
from dashboard.components.tables import render_table
from dashboard.utils.data_loader import load_benchmark_results
from dashboard.utils.filters import filter_df, sidebar_filters
from src.benchmark.metrics import all_metrics, confusion_counts, roc

st.title("📈 Benchmark Results — Resultados detallados")

df = load_benchmark_results()
if df.empty:
    st.error("No hay resultados guardados todavía. Ejecuta `python scripts/run_benchmark.py`.")
    st.stop()

with st.sidebar.expander("Filtros del benchmark", expanded=True):
    ds, decision, success = sidebar_filters(df, key_prefix="bm2")

filtered = filter_df(df, ds, decision, success)

m = all_metrics(filtered)
tp, fp, fn, tn, _ = confusion_counts(filtered)

# ---------------------------------------------------------------- charts
section_header("Gráficas comparativas")
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(charts.plot_asr_comparison(m), width="stretch")
with c2:
    st.plotly_chart(charts.plot_confusion_matrix(tp, fp, fn, tn), width="stretch")

c3, c4 = st.columns(2)
with c3:
    st.plotly_chart(charts.plot_performance_by_attack_type(filtered), width="stretch")
with c4:
    roc_data = roc(filtered)
    st.plotly_chart(charts.plot_roc_curve(roc_data), width="stretch")

# ---------------------------------------------------------------- table
section_header("Tabla interactiva de resultados")
st.caption(f"Mostrando {len(filtered)} de {len(df)} filas · "
           f"Precisión {m['precision']:.3f} · Recall {m['recall']:.3f} · F1 {m['f1']:.3f}")
render_table(filtered, key="bm_table", height=460)