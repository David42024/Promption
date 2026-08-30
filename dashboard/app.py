"""Prompt Injection Filter — interactive Streamlit dashboard.

Run:  streamlit run dashboard/app.py
"""
import os
from pathlib import Path

import streamlit as st

from dashboard.utils.data_loader import api_health, api_reachable, latest_benchmark_timestamp
from dashboard.utils.theme import css_string

st.set_page_config(
    page_title="Prompt Injection Filter — Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

ASSETS = Path(__file__).resolve().parent / "assets"


def _inject_css() -> None:
    st.markdown(css_string(), unsafe_allow_html=True)
    css = ASSETS / "css" / "custom.css"
    if css.exists():
        st.markdown(f"<style>{css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


_inject_css()


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    logo = ASSETS / "images" / "logo.png"
    if logo.exists():
        st.image(str(logo), width=120)
    st.markdown("## 🛡️ Prompt Injection Filter")
    st.caption("Sistema anti-prompt-injection en dos capas\nheurística + embeddings/RandomForest")

    st.divider()
    st.markdown("### 🔍 Navegación")
    st.caption("Usa el menú de la parte superior para cambiar de página.")

    api_up = api_reachable()
    st.divider()
    st.markdown("### ⚙️ Estado del sistema")
    st.markdown(f"**API FastAPI:** {'✅ conectada' if api_up else '❌ sin conexión'}")

    health = api_health()
    ollama = health.get("ollama", {})
    connected = bool(ollama.get("connected"))
    st.markdown(f"**Ollama:** {'✅ conectado' if connected else '❌ desconectado'}")
    if ollama.get("models"):
        st.caption("Modelos: " + ", ".join(ollama["models"][:3]))

    last_ts = latest_benchmark_timestamp()
    st.markdown(f"**Último benchmark:** {last_ts}")

    if st.button("🔄 Refrescar datos", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown(
        '<div style="font-size:0.72rem;color:#8B93A1;text-align:center;">'
        "Proyecto académico · Detección de Prompt Injection<br/>"
        f"Entorno: {os.name} · API: {'ON' if api_up else 'OFF'}</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:0.4rem;">
        <h1 style="margin:0;font-size:2rem;">Prompt Injection Filter</h1>
        <span style="color:#9AA3B2;">Dashboard de evaluación y monitoreo</span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()
st.info(
    "Selecciona una página desde el menú superior. "
    "Los datos se leen de `data/results/` y se refrescan automáticamente "
    "cuando ejecutas un nuevo benchmark."
)