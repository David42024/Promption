"""Página 2 — Benchmark Results: análisis detallado por capa y confidencialidad."""
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
from dashboard.components.metrics import kpi_card, pct, section_header
from dashboard.components.sidebar import setup_page
from dashboard.components.tables import render_table
from dashboard.utils.data_loader import load_benchmark_results
from dashboard.utils.filters import filter_df, sidebar_filters
from promption.benchmark.metrics import all_metrics, confusion_counts, evaluated_confusion_counts, roc

setup_page("Benchmark Results — Prompt Injection Filter", "📈")

st.title("📈 Benchmark Results — Evaluación por capa y confidencialidad")

df = load_benchmark_results()
if df.empty:
    st.error("No hay resultados guardados todavía. Ejecuta `python scripts/run_benchmark.py`.")
    st.stop()

with st.sidebar.expander("Filtros del benchmark", expanded=True):
    ds, decision, success = sidebar_filters(df, key_prefix="bm2")

filtered = filter_df(df, ds, decision, success)

m = all_metrics(filtered)

# ---------------------------------------------------------------- metrics overview
st.caption(f"**Tamaño de muestra evaluado:** {len(filtered)} de {len(df)} casos totales | "
           f"Maliciosos: {m['n_malicious']} | Benignos: {m['n_benign']}")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    kpi_card("Precisión Ensemble", pct(m.get("precision")), good_when="high", severity=m.get("precision"))
with col2:
    kpi_card("Recall Ensemble", pct(m.get("recall")), good_when="high", severity=m.get("recall"))
with col3:
    kpi_card("F1-Score", pct(m.get("f1")), good_when="high", severity=m.get("f1"))
with col4:
    kpi_card("Fugas Prevenidas", str(m.get("secret_leaks_prevented", 0)),
             help_text="Secretos neutralizados por Output Guard",
             good_when="high", severity=1.0 if m.get("secret_leaks_prevented", 0) > 0 else 0.5)
with col5:
    kpi_card("Errores Proveedor", str(m.get("provider_errors", 0)),
             help_text="Excluidos del denominador evaluable",
             good_when="low", severity=0.0 if m.get("provider_errors", 0) == 0 else 1.0)

# ---------------------------------------------------------------- confidentiality & layers
section_header("Confidencialidad y Fugas de Información")
conf_m = m.get("confidentiality", {})
st.caption(
    f"**ASR Estricto Protegido (Integral):** {pct(conf_m.get('strict_asr_with_filter'))} "
    f"({conf_m.get('leaks_with_protection', 0)} fugas en {conf_m.get('evaluable_protected_cases', 0)} ataques evaluables) · "
    f"**Reducción en pares comparables:** {pct(conf_m.get('strict_asr_reduction'))} "
    f"({conf_m.get('comparable_cases', 0)} pares) · "
    f"**Output Guard:** {conf_m.get('guard_evaluable_cases', 0)} evaluados en generación"
)
c_conf1, c_conf2 = st.columns(2)
with c_conf1:
    charts.render_chart(charts.plot_leaks_before_after(filtered))
with c_conf2:
    charts.render_chart(charts.plot_asr_comparison(m))

# ---------------------------------------------------------------- confusion matrices
section_header("Matrices de Confusión por Detector")
tab_ensemble, tab_heur, tab_ml, tab_containment = st.tabs([
    "Ensemble / Filtro", "Detector Heurístico", "Detector ML", "Contención Final"
])

with tab_ensemble:
    tp, fp, fn, tn, _ = confusion_counts(filtered, label_col="label", pred_col="filter_blocked")
    charts.render_chart(charts.plot_confusion_matrix(tp, fp, fn, tn, title="Matriz de confusión — Ensemble Input Filter"))

with tab_heur:
    if "heuristic_blocked" in filtered.columns:
        tp_h, fp_h, fn_h, tn_h, det_h = evaluated_confusion_counts(filtered, label_col="label", pred_col="heuristic_blocked")
        st.caption(f"Evaluados: {det_h['evaluated']} · Omitidos: {det_h['skipped']}")
        charts.render_chart(charts.plot_confusion_matrix(tp_h, fp_h, fn_h, tn_h, title="Matriz de confusión — Capa Heurística"))
    else:
        st.info("Columna 'heuristic_blocked' no disponible.")

with tab_ml:
    if "ml_blocked" in filtered.columns and filtered["ml_blocked"].notna().sum() > 0:
        tp_m, fp_m, fn_m, tn_m, det_m = evaluated_confusion_counts(filtered, label_col="label", pred_col="ml_blocked")
        st.caption(f"Evaluados: {det_m['evaluated']} · Omitidos: {det_m['skipped']}")
        charts.render_chart(charts.plot_confusion_matrix(tp_m, fp_m, fn_m, tn_m, title="Matriz de confusión — Capa ML"))
    else:
        st.info("Capa ML no ejecutada u omitida en este subconjunto (N/A).")

with tab_containment:
    pred_cont = "final_blocked" if "final_blocked" in filtered.columns else "filter_blocked"
    tp_c, fp_c, fn_c, tn_c, det_c = evaluated_confusion_counts(filtered, label_col="label", pred_col=pred_cont)
    st.caption(f"Evaluados: {det_c['evaluated']} · Protección integral de extremo a extremo")
    charts.render_chart(charts.plot_confusion_matrix(tp_c, fp_c, fn_c, tn_c, title="Matriz de confusión — Contención Integral del Sistema"))

# ---------------------------------------------------------------- layer & latency charts
section_header("Distribución de Intervenciones y Latencias")
c3, c4 = st.columns(2)
with c3:
    charts.render_chart(charts.plot_layer_blocks(filtered))
with c4:
    charts.render_chart(charts.plot_latency_breakdown(filtered))

c5, c6 = st.columns(2)
with c5:
    charts.render_chart(charts.plot_performance_by_attack_type(filtered))
with c6:
    roc_data = roc(filtered)
    charts.render_chart(charts.plot_roc_curve(roc_data))

# ---------------------------------------------------------------- table
section_header("Tabla interactiva de resultados por caso y capa")
st.caption(f"Mostrando {len(filtered)} filas con desglose de inspección.")
render_table(filtered, key="bm_table", height=480)
