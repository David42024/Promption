"""Página 7 — PDF Testing: adjuntar PDFs y verificar el filtro sobre documentos."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve()
while not (_ROOT / "src").exists() and _ROOT.parent != _ROOT:
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import plotly.graph_objects as go
import streamlit as st

from dashboard.components import charts
from dashboard.components.metrics import section_header
from dashboard.components.sidebar import setup_page
from dashboard.utils.filter_runner import filter_text
from dashboard.utils.theme import get_palette
from src.utils.pdf_extractor import extract_pdf_pages

MAX_PAGES = 40

setup_page("PDF Testing — Prompt Injection Filter", "📄")

st.title("📄 PDF Testing — Filtro sobre documentos")
st.caption("Adjunta uno o más PDF. El texto se extrae por página y cada página se analiza con el filtro "
           "completo (heurística + ML). Un documento se considera bloqueado si cualquiera de sus páginas lo está.")

uploaded = st.file_uploader("Adjunta PDFs", type=["pdf"], accept_multiple_files=True)

if not uploaded:
    st.info("Sube uno o más PDF para empezar.")
    st.stop()

for file in uploaded:
    try:
        pages = extract_pdf_pages(file.getvalue())[:MAX_PAGES]
    except Exception as exc:  # noqa: BLE001
        st.error(f"**{file.name}** no se pudo leer: {exc}")
        continue
    if not pages:
        st.warning(f"**{file.name}** sin texto extraíble (¿PDF escaneado o solo imágenes?).")
        continue

    results = [filter_text(p) for p in pages]
    blocked_pages = [i + 1 for i, r in enumerate(results) if r["blocked"]]
    max_conf = max((r["confidence"] for r in results), default=0.0)

    st.markdown(f"### {file.name}")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Páginas analizadas", len(results))
    with c2:
        st.metric("Páginas bloqueadas", len(blocked_pages))
    with c3:
        st.metric("Confianza máx.", f"{max_conf:.2f}")

    if blocked_pages:
        st.error("🚫 BLOQUEADO — páginas: " + ", ".join(map(str, blocked_pages)))
    else:
        st.success("✅ PERMITIDO — ninguna página fue bloqueada.")

    pal = get_palette()
    fig = go.Figure(go.Bar(
        x=[f"Página {i + 1}" for i in range(len(results))],
        y=[r["confidence"] for r in results],
        marker_color=[pal["red"] if r["blocked"] else pal["blue"] for r in results],
        text=[f"{r['confidence']:.2f}" for r in results],
        textposition="outside",
    ))
    charts.apply_theme(fig, title="Confianza por página (rojo = bloqueada)", height=260, yaxis_title="Confianza")
    charts.render_chart(fig, key=f"conf_chart_{file.name}")

    with st.expander("Ver texto extraído y detalles por página", expanded=False):
        for i, (page, r) in enumerate(zip(pages, results), 1):
            st.markdown(f"**Página {i}** — {r['decision']} · confianza `{r['confidence']:.2f}` · "
                        f"{r['latency_ms']:.1f} ms")
            if r["heuristic"]["matched_rules"]:
                st.markdown("Reglas: " + ", ".join(rule["name"] for rule in r["heuristic"]["matched_rules"][:5]))
            st.code(page[:800], language="text")
            st.divider()

    with st.expander("Comparar una página con el LLM", expanded=False):
        sel = st.selectbox("Página a enviar al LLM", options=range(1, len(results) + 1),
                           format_func=lambda p: f"Página {p}", key=f"llm_page_{file.name}")
        if st.button("⚡ Consultar LLM", key=f"llm_btn_{file.name}"):
            from src.benchmark.runner import SYSTEM_PROMPT, is_compromised
            from src.llm import get_llm_client

            idx = sel - 1
            with st.spinner("Consultando LLM…"):
                client = get_llm_client()
                health = client.health()
                if not health["connected"]:
                    st.error(f"LLM no responde en {health['host']}. Configura PIF_LLM_API_KEY o inicia `ollama serve`. Detalle: {health.get('error')}")
                else:
                    try:
                        r0 = client.generate(pages[idx], system=SYSTEM_PROMPT)
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"No se pudo consultar el LLM: {exc}")
                        st.stop()
                    if is_compromised(r0.text):
                        st.error("⚠ El LLM reveló el código secreto (¿debería haber sido bloqueado?).")
                    else:
                        st.success("El LLM se negó a revelar el secreto.")
                    st.text_area("Respuesta del LLM", r0.text[:600], height=140, key=f"llm_resp_{file.name}")

section_header("Nota")
st.caption("Los PDFs se leen en memoria (pypdf). Los documentos escaneados (solo imágenes) requieren OCR, "
           "que está fuera del alcance de este proyecto.")