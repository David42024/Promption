"""Página 6 — System Health: estado del sistema y rendimiento."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve()
while not (_ROOT / "src").exists() and _ROOT.parent != _ROOT:
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json
import time
from pathlib import Path

import psutil
import streamlit as st

from dashboard.components.metrics import kpi_card, section_header, status_badge
from dashboard.utils.data_loader import api_health, api_reachable
from dashboard.utils.paths import CONFIG_DIR, MODELS_DIR, RESULTS_DIR
from src.filter.ensemble_filter import EnsembleFilter
from src.llm.ollama_client import OllamaClient

st.title("⚡ System Health — Estado del sistema")

def _fmt_uptime(boot_ts: float) -> str:
    secs = int(time.time() - boot_ts)
    d = secs // 86400
    h = (secs % 86400) // 3600
    m = (secs % 3600) // 60
    return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"

health = api_health()
filter_obj = EnsembleFilter()

# ------------------------------------------------------------------ services
section_header("Servicios")
c1, c2, c3 = st.columns(3)
with c1:
    status_badge("API FastAPI (localhost:8000)", api_reachable())
with c2:
    ollama = health.get("ollama", {})
    status_badge(f"Ollama ({ollama.get('host', '…')})", bool(ollama.get("connected")))
with c3:
    status_badge("Modelo ML (random_forest.pkl)", MODELS_DIR.joinpath("random_forest.pkl").exists())

# ------------------------------------------------------------------ resources
section_header("Recursos del sistema")
mem = psutil.virtual_memory()
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Memoria RAM usada", f"{mem.percent}%", f"{mem.used / 1e9:.1f} / {mem.total / 1e9:.1f} GB",
             good_when="low", severity=mem.percent / 100)
with c2:
    kpi_card("CPU (instante)", f"{psutil.cpu_percent(interval=0.3)}%", "", good_when="low")
with c3:
    kpi_card("Uptime del dashboard", _fmt_uptime(psutil.boot_time()), "")
with c4:
    layers = filter_obj.layers_status()
    kpi_card("Reglas heurísticas", str(layers.get("heuristic_rules", 0)), "cargadas desde heuristics.yaml")

# ------------------------------------------------------------------ ollama
section_header("Modelos disponibles en Ollama")
if ollama.get("models"):
    st.write(" · ".join(ollama["models"]))
else:
    st.warning("Ollama no responde o no tiene modelos. Verifica: `ollama list`")

# ------------------------------------------------------------------ logs
section_header("Logs recientes")
log_path = Path(__file__).resolve().parents[2] / "logs" / "system.log"
if log_path.exists():
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
    st.code("\n".join(lines), language="text")
else:
    st.info("Sin logs todavía.")

# ------------------------------------------------------------------ config
section_header("Configuración actual")
with st.expander("Ver config.yaml", expanded=False):
    cfg_path = CONFIG_DIR / "config.yaml"
    if cfg_path.exists():
        st.code(cfg_path.read_text(encoding="utf-8"), language="yaml")

# ------------------------------------------------------------------ actions
section_header("Acciones de mantenimiento")
c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 Recargar filtro (heurísticas + ML)", type="primary", width="stretch"):
        EnsembleFilter._instance = None
        st.cache_resource.clear()
        st.success("Filtro recargado. Capas: " + json.dumps(EnsembleFilter().layers_status()))
with c2:
    if st.button("🧪 Probar conexión de todos los servicios", width="stretch"):
        results = {
            "API FastAPI": api_reachable(),
            "Ollama": bool(ollama.get("connected")),
            "Modelo ML": MODELS_DIR.joinpath("random_forest.pkl").exists(),
            "Datos de benchmark": RESULTS_DIR.joinpath("benchmark_results.csv").exists(),
        }
        for name, ok in results.items():
            st.markdown(f"- {name}: {'✅ OK' if ok else '❌ FALLO'}")