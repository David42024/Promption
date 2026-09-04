"""Página 8 — Audio Testing: transcribir audios y verificar el filtro sobre el texto."""
import sys
from io import BytesIO
from pathlib import Path

_ROOT = Path(__file__).resolve()
while not (_ROOT / "src").exists() and _ROOT.parent != _ROOT:
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from dashboard.components.metrics import section_header
from dashboard.components.sidebar import setup_page
from dashboard.utils.filter_runner import filter_text
from src.utils.audio_transcriber import load_stt_model, transcribe

AUDIO_EXT = ["wav", "mp3", "m4a", "ogg", "flac"]

setup_page("Audio Testing — Prompt Injection Filter", "🎧")

st.title("🎧 Audio Testing — Filtro sobre transcripciones")
st.caption("Adjunta audio (WAV/MP3/M4A/OGG/FLAC). Se transcribe localmente con faster-whisper "
           "(modelo 'tiny', sin nubes) y el texto obtenido se analiza con el filtro completo.")

@st.cache_resource(show_spinner="Cargando modelo de transcripción (faster-whisper) — la 1ª vez se descarga…")
def _stt():
    return load_stt_model()


uploaded = st.file_uploader("Adjunta audios", type=AUDIO_EXT, accept_multiple_files=True)

if not uploaded:
    st.info("Sube uno o más audios para empezar.")
    st.stop()

for file in uploaded:
    st.markdown(f"### {file.name}")
    try:
        with st.spinner("Transcribiendo…"):
            text = transcribe(BytesIO(file.getvalue()), model=_stt())
    except Exception as exc:  # noqa: BLE001
        st.error(f"**{file.name}** no se pudo transcribir: {exc}")
        continue
    if not text:
        st.warning(f"**{file.name}** sin audio reconocible.")
        continue

    result = filter_text(text)
    if result["blocked"]:
        st.error("🚫 BLOQUEADO")
    else:
        st.success("✅ PERMITIDO")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Confianza (score)", f"{result['confidence']:.2f}")
    with c2:
        st.metric("Latencia del filtro", f"{result['latency_ms']:.1f} ms")
    with c3:
        st.metric("Capa decisora", "Ensemble + " + (result["reason"] or "permitido"))

    st.text_area("Transcripción del audio", text, height=160, key=f"transcript_{file.name}")

    with st.expander("Detalle de capas", expanded=False):
        heur = result["heuristic"]
        ml = result["ml"]
        st.markdown(f"**Heurística** — score {heur['score']:.2f} (umbral {heur['threshold']})")
        if heur["matched_rules"]:
            st.markdown("Reglas: " + ", ".join(r["name"] for r in heur["matched_rules"][:5]))
        if ml["available"]:
            st.markdown(f"**ML** — probabilidad {ml['probability']:.3f} · bloqueado {ml['blocked']}")
        else:
            st.markdown("**ML** — no disponible")

    with st.expander("Comparar la transcripción con el LLM", expanded=False):
        if st.button("⚡ Consultar LLM", key=f"llm_btn_{file.name}"):
            from src.benchmark.runner import SYSTEM_PROMPT, is_compromised
            from src.llm import get_llm_client

            with st.spinner("Consultando LLM…"):
                client = get_llm_client()
                health = client.health()
                if not health["connected"]:
                    st.error(f"LLM no responde en {health['host']}. Configura PIF_LLM_API_KEY o inicia `ollama serve`. Detalle: {health.get('error')}")
                else:
                    try:
                        r0 = client.generate(text, system=SYSTEM_PROMPT)
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"No se pudo consultar el LLM: {exc}")
                        st.stop()
                    if is_compromised(r0.text):
                        st.error("⚠ El LLM reveló el código secreto.")
                    else:
                        st.success("El LLM se negó a revelar el secreto.")
                    st.text_area("Respuesta del LLM", r0.text[:600], height=140,
                                 key=f"llm_resp_{file.name}")

section_header("Nota")
st.caption("La transcripción se hace en local (faster-whisper 'tiny'). La primera ejecución descarga el modelo "
           "desde HuggingFace; después queda cacheado. Para fragmentos largos se recomienda 'small' "
           "editable en `config/config.yaml` (sección `stt.model`).")