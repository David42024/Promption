"""Página 1 — Overview: KPIs principales agrupados por categoría."""
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
from dashboard.components.sidebar import setup_page
from dashboard.utils.data_loader import (
    api_health,
    latest_benchmark_timestamp,
    load_benchmark_results,
    load_latest_json,
)
from src.benchmark.metrics import all_metrics

setup_page("Overview — Prompt Injection Filter", "📊")

st.title("📊 Overview — Visión general")
st.caption("Indicadores clave del filtro sobre el último benchmark ejecutado.")


def _kpi_group(title: str, subtitle: str, cards: list[tuple]) -> None:
    """Render a titled group of kpi_card specs in rows of `cols` columns.

    Spec: (icon, label, value, help_text, good_when, severity).
    """
    section_header(title, subtitle)
    cols_count = len(cards)
    for i in range(0, len(cards), cols_count):
        row = cards[i:i + cols_count]
        c = st.columns(cols_count)
        for col, (icon, label, value, help_text, good_when, severity) in zip(c, row):
            with col:
                kpi_card(label, value, help_text, good_when=good_when, severity=severity, icon=icon)


df = load_benchmark_results()
payload = load_latest_json()

if df.empty:
    st.error("Todavía no hay resultados. Ejecuta la evaluación con:")
    st.code("python scripts/run_benchmark.py --no-llm\n# o desde la API: POST /api/v1/benchmark",
            language="bash")
    st.stop()

m = all_metrics(df)
lat = m.get("latency", {})
health = api_health()
ollama_ok = bool(health.get("ollama", {}).get("connected"))

# ---------------------------------------------------------------- KPIs
_kpi_group(
    "⚔️ Efectividad del filtro",
    "Cuánto reduce el ataque sobre el LLM cuando está activo.",
    [
        ("🎯", "ASR sin filtro", pct(m["asr_without_filter"]),
         "Tasa de éxito del ataque sobre el LLM desnudo", "low", m["asr_without_filter"]),
        ("🛡️", "ASR con filtro", pct(m["asr_with_filter"]),
         "Tasa de éxito tras pasar por el filtro", "low", m["asr_with_filter"]),
        ("📉", "Reducción de ASR", pct(m["asr_reduction"]),
         "Mejora relativa al aplicar el filtro", "high", m["asr_reduction"]),
    ],
)

_kpi_group(
    "🧠 Calidad de detección",
    "Precisión, cobertura y errores del clasificador binario.",
    [
        ("🎯", "Precisión", pct(m["precision"]),
         "De lo bloqueado, cuánto era realmente malicioso", "high", m["precision"]),
        ("🔍", "Recall", pct(m["recall"]),
         "De lo malicioso, cuánto se bloqueó", "high", m["recall"]),
        ("🧮", "F1-Score", pct(m["f1"]),
         "Media armónica precisión-recall", "high", m["f1"]),
        ("✅", "Falsos positivos (FPR)", pct(m["fpr"]),
         "Benignos bloqueados por error", "low", m["fpr"]),
        ("❌", "Falsos negativos (FNR)", pct(m["fnr"]),
         "Maliciosos que pasaron el filtro", "low", m["fnr"]),
    ],
)

_kpi_group(
    "⚡ Rendimiento",
    "Tiempo de decisión del filtro (heurística + ML).",
    [
        ("⏱️", "Latencia media", f"{lat.get('mean', 0) / 1000:.1f} ms",
         "Tiempo total de decisión del filtro", "low", min(lat.get("mean", 0) / 1000 / 2000, 1)),
        ("🚀", "p95 latencia", f"{lat.get('p95', 0) / 1000:.1f} ms",
         "Percentil 95 de latencia", "low", min(lat.get("p95", 0) / 1000 / 2000, 1)),
    ],
)

_kpi_group(
    "🖥️ Sistema",
    "Cantidad de datos evaluados y disponibilidad del LLM.",
    [
        ("📦", "Muestras totales", str(m["n_total"]),
         f"{m['n_malicious']} maliciosas · {m['n_benign']} benignas",
         "high", min(m["n_total"] / 2000, 1)),
        ("🤖", "LLM (Ollama)", "✅ Operativo" if ollama_ok else "⚠ Sin conexión",
         "Se usa para medir el ASR real" if ollama_ok else "ASR calculado con proxy determinista",
         "high", 1.0 if ollama_ok else 0.0),
    ],
)

# ---------------------------------------------------------------- charts
section_header("Comparativa y distribuciones",
               "ASR antes/después y distribución de confianza del ensemble.")
left, right = st.columns(2)
with left:
    charts.render_chart(charts.plot_asr_comparison(m))
with right:
    charts.render_chart(charts.plot_confidence_distribution(df))

st.divider()
st.markdown(f"**Última ejecución del benchmark:** `{latest_benchmark_timestamp()}`")
if payload.get("options"):
    st.caption(f"Opciones: {payload['options']}")