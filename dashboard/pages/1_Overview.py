"""Página 1 — Overview: KPIs principales."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve()
while not (_ROOT / "src").exists() and _ROOT.parent != _ROOT:
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from dashboard.components import charts
from dashboard.components.metrics import kpi_card, pct, section_header
from dashboard.utils.data_loader import (
    api_health,
    latest_benchmark_timestamp,
    load_benchmark_results,
    load_latest_json,
)
from dashboard.utils.paths import MODELS_DIR
from src.benchmark.metrics import all_metrics

st.title("📊 Overview — Visión general")

df = load_benchmark_results()
payload = load_latest_json()

if df.empty:
    st.error("Todavía no hay resultados. Ejecuta la evaluación con:")
    st.code("python scripts/run_benchmark.py --no-llm\n# o desde la API: POST /api/v1/benchmark",
            language="bash")
    st.stop()

m = all_metrics(df)
lat = m.get("latency", {})

# ---------------------------------------------------------------- KPI cards
section_header("Métricas clave")
c = st.columns(6)
with c[0]:
    kpi_card("ASR sin filtro", pct(m["asr_without_filter"]), "Tasa de éxito del ataque sobre el LLM desnudo",
             good_when="low", severity=m["asr_without_filter"])
with c[1]:
    kpi_card("ASR con filtro", pct(m["asr_with_filter"]), "Tasa de éxito tras pasar por el filtro",
             good_when="low", severity=m["asr_with_filter"])
with c[2]:
    kpi_card("Reducción de ASR", pct(m["asr_reduction"]), "Mejora relativa al aplicar el filtro",
             good_when="high", severity=m["asr_reduction"])
with c[3]:
    kpi_card("Precisión", pct(m["precision"]), "De lo bloqueado, cuánto era realmente malicioso",
             severity=m["precision"])
with c[4]:
    kpi_card("Recall", pct(m["recall"]), "De lo malicioso, cuánto se bloqueó",
             severity=m["recall"])
with c[5]:
    kpi_card("F1-Score", pct(m["f1"]), "Media armónica precisión-recall", severity=m["f1"])

c = st.columns(6)
with c[0]:
    kpi_card("Falsos positivos (FPR)", pct(m["fpr"]), "Benignos bloqueados por error",
             good_when="low", severity=m["fpr"])
with c[1]:
    kpi_card("Falsos negativos (FNR)", pct(m["fnr"]), "Maliciosos que pasaron el filtro",
             good_when="low", severity=m["fnr"])
with c[2]:
    kpi_card("Latencia media", f"{lat.get('mean', 0) / 1000:.1f} ms", "Tiempo total de decisión del filtro",
             good_when="low", severity=min(lat.get("mean", 0) / 1000 / 2000, 1))
with c[3]:
    kpi_card("p95 latencia", f"{lat.get('p95', 0) / 1000:.1f} ms", "Percentil 95 de latencia",
             good_when="low", severity=min(lat.get("p95", 0) / 1000 / 2000, 1))
with c[4]:
    kpi_card("Muestras totales", str(m["n_total"]), f"{m['n_malicious']} maliciosas · {m['n_benign']} benignas")
with c[5]:
    health = api_health()
    ok = bool(health.get("ollama", {}).get("connected"))
    kpi_card("LLM (Ollama)", "✅ Operativo" if ok else "⚠ Sin conexión",
             "Se usa para medir el ASR real" if ok else "ASR calculado con proxy determinista",
             good_when="high", severity=1.0 if ok else 0.0)

# ---------------------------------------------------------------- charts
section_header("Comparativa y distribuciones")
left, right = st.columns(2)
with left:
    st.plotly_chart(charts.plot_asr_comparison(m), width="stretch")
with right:
    conf = df["ensemble_score"].astype(float)
    import plotly.express as px
    fig = px.histogram(conf, nbins=40, title="Distribución de confianza del ensemble",
                       color_discrete_sequence=["#4F46E5"], labels={"value": "Score", "count": "Frecuencia"})
    fig.update_layout(template="plotly_white", title=dict(x=0.5, xanchor="center"))
    st.plotly_chart(fig, width="stretch")

st.divider()
st.markdown(f"**Última ejecución del benchmark:** `{latest_benchmark_timestamp()}`")
if payload.get("options"):
    st.caption(f"Opciones: {payload['options']}")