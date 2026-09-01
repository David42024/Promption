"""Página 2 — Benchmark Results: análisis detallado."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve()
while not (_ROOT / "src").exists() and _ROOT.parent != _ROOT:
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

from dashboard.components import charts
from dashboard.components.metrics import section_header
from dashboard.components.sidebar import setup_page
from dashboard.components.tables import render_table
from dashboard.utils.data_loader import load_benchmark_results
from dashboard.utils.filters import filter_df, sidebar_filters
from src.benchmark.metrics import all_metrics, confusion_counts, roc

setup_page("Benchmark Results — Prompt Injection Filter", "📈")

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
    charts.render_chart(charts.plot_asr_comparison(m))
with c2:
    charts.render_chart(charts.plot_confusion_matrix(tp, fp, fn, tn))

c3, c4 = st.columns(2)
with c3:
    charts.render_chart(charts.plot_performance_by_attack_type(filtered))
with c4:
    roc_data = roc(filtered)
    charts.render_chart(charts.plot_roc_curve(roc_data))

# ---------------------------------------------------------------- table
section_header("Tabla interactiva de resultados")
st.caption(f"Mostrando {len(filtered)} de {len(df)} filas · "
           f"Precisión {m['precision']:.3f} · Recall {m['recall']:.3f} · F1 {m['f1']:.3f}")
render_table(filtered, key="bm_table", height=460)