"""Prompt Injection Filter — interactive Streamlit dashboard.

Run:  streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve()
while not (_ROOT / "src").exists() and _ROOT.parent != _ROOT:
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from dashboard.components.metrics import info_card, section_header
from dashboard.components.sidebar import setup_page
from dashboard.utils.theme import get_palette

setup_page("Prompt Injection Filter — Dashboard", "🛡️")

pal = get_palette()

# ------------------------------------------------------------------- hero
st.markdown(
    f"""
    <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:14px;margin:0.4rem 0 0.2rem;">
        <h1 style="margin:0;font-size:2.15rem;color:{pal['text']};">Prompt Injection Filter</h1>
        <span style="color:{pal['text_muted']};">Dashboard de evaluación y monitoreo</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    f'<p style="color:{pal["text_muted"]};max-width:70rem;">Sistema anti-prompt-injection en dos capas — '
    "heurística + embeddings/RandomForest. Explora métricas, prueba prompts en vivo y evalúa documentos "
    "PDF o transcripciones de audio.</p>",
    unsafe_allow_html=True,
)

st.divider()

# --------------------------------------------------- description as cards
section_header(
    "Qué muestra este dashboard",
    "Ocho módulos para evaluar y monitorizar el filtro frente a inyecciones de prompt.",
)

_pages = [
    ("📊", "Overview", "Indicadores clave: ASR con/sin filtro, reducción, precisión/recall/F1, falsos positivos, negativos y latencia."),
    ("📈", "Benchmark Results", "Tabla interactiva de cada prompt evaluado, distribución por dataset y tipo de ataque, curva ROC."),
    ("🔬", "Model Analysis", "Importancia de variables (embeddings), PCA, correlaciones, análisis de errores y ajuste del umbral."),
    ("🧪", "Real-Time Testing", "Escribe un prompt y mira al instante qué capa decide, con qué confianza, y compáralo con Ollama."),
    ("🎯", "Attack Analysis", "Top payloads que superan el filtro, distribución por tipo de ataque y patrones comunes."),
    ("⚡", "System Health", "Estado de Ollama y la API, recursos del sistema, logs y configuración actual."),
    ("📄", "PDF Testing", "Adjunta un PDF: se extrae el texto por página y cada página se analiza con el filtro."),
    ("🎧", "Audio Testing", "Adjunta audio (WAV/MP3…), se transcribe en local y el texto se analiza con el filtro."),
]
for i in range(0, len(_pages), 4):
    row = _pages[i:i + 4]
    cols = st.columns(4)
    for col, (icon, title, desc) in zip(cols, row):
        with col:
            info_card(icon, title, desc)

st.divider()

# ----------------------------------------------------------- how to start
section_header("Cómo empezar", "Tres pasos para regenerar datos y explorar el dashboard.")
_steps = [
    ("1", "Genera datos",
     "Ejecuta el pipeline de entrenamiento y benchmark: <br/><code>python scripts/run_benchmark.py --no-llm</code> "
     "<br/>Los resultados se guardan en <code>data/results/</code> (CSV, JSON y gráficas)."),
    ("2", "Abre el dashboard",
     "Selecciona una página desde el menú superior. Los datos se cargan automáticamente al iniciar y se "
     "refrescan cuando ejecutas un nuevo benchmark."),
    ("3", "Refresca a demanda",
     "Pulsa el botón <b>Refrescar datos</b> de la barra lateral para forzar la recarga inmediata sin reiniciar el servidor."),
]
cols = st.columns(3)
for col, (num, title, body) in zip(cols, _steps):
    with col:
        info_card(f'<b style="font-size:1.5rem;color:{pal["primary"]};">{num}</b>', title, body)