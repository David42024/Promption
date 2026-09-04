"""Shared sidebar chrome: logo, navigation, theme toggle and system status.

Every page (including the Home/app.py) calls setup_page() at the top so the
branding, the light/dark toggle and the system state render identically in all
pages, instead of duplicating the HTML/logic in each script.
"""
import os
from pathlib import Path

import streamlit as st

from dashboard.utils.data_loader import API_URL, api_health, api_reachable, latest_benchmark_timestamp
from dashboard.utils.theme import get_palette, inject_css

_ASSETS = Path(__file__).resolve().parents[1] / "assets"


def get_theme_mode() -> str:
    """Current theme mode ('dark' or 'light'), persisted in session_state."""
    return st.session_state.get("theme_mode", "dark")


def render_theme_toggle() -> str:
    """st.toggle once at the top of the sidebar; writes session_state['theme_mode']."""
    current = get_theme_mode()
    st.toggle(
        "☀️ Modo claro",
        value=current == "light",
        key="theme_toggle",
        help="Cambia entre tema oscuro y claro. Se aplica a todo el dashboard.",
    )
    mode = "light" if st.session_state.theme_toggle else "dark"
    st.session_state["theme_mode"] = mode
    return mode


def render_sidebar() -> None:
    with st.sidebar:
        logo = _ASSETS / "images" / "logo.png"
        if logo.exists():
            st.image(str(logo), width=120)
        st.markdown("## 🛡️ Prompt Injection Filter")
        st.caption("Sistema anti-prompt-injection en dos capas\nheurística + embeddings/RandomForest")

        render_theme_toggle()

        st.divider()
        st.markdown("### 🔍 Navegación")
        st.caption("Usa el menú de la parte superior para cambiar de página.")

        api_up = api_reachable()
        st.divider()
        st.markdown("### ⚙️ Estado del sistema")
        st.markdown(f"**API FastAPI:** {'✅ conectada' if api_up else '❌ sin conexión'}")
        st.caption(f"{API_URL}/api/v1/health")

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
        pal = get_palette()
        st.markdown(
            f'<div style="font-size:0.72rem;color:{pal["text_muted"]};text-align:center;">'
            "Proyecto académico · Detección de Prompt Injection<br/>"
            f"Entorno: {os.name} · API: {'ON' if api_up else 'OFF'}</div>",
            unsafe_allow_html=True,
        )


def setup_page(page_title: str, page_icon: str = "🛡️") -> None:
    """Single entry-point per page: page config (wide/expanded) + CSS + shared sidebar."""
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()
    render_sidebar()