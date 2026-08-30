"""Interactive tables (search/sort/pagination via st.dataframe + export)."""
import pandas as pd
import streamlit as st


def style_result_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.rename(columns={
        "prompt": "Prompt",
        "dataset": "Dataset",
        "attack_type": "Tipo de ataque",
        "label": "Etiqueta",
        "heuristic_score": "Score heurística",
        "ml_probability": "Prob. ML",
        "ensemble_score": "Score ensemble",
        "filter_blocked": "Bloqueado",
        "filter_latency_ms": "Latencia (s)",
        "llm_success_with_filter": "Engañó al LLM (filtrado)",
        "llm_success_no_filter": "Engañó al LLM (sin filtro)",
    })
    for col in ("Score heurística", "Prob. ML", "Score ensemble"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(3)
    if "Latencia (s)" in out.columns:
        out["Latencia (s)"] = pd.to_numeric(out["Latencia (s)"], errors="coerce").round(2)
    return out


def render_table(df: pd.DataFrame, key: str = "table", height: int = 420, download: bool = True) -> None:
    if df.empty:
        st.info("No hay datos que mostrar. Ejecuta un benchmark primero.")
        return

    shown = style_result_table(df)
    st.dataframe(shown, hide_index=True, height=height)

    if download:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(":inbox_tray: Exportar CSV", data=csv, file_name="resultados_benchmark.csv",
                           mime="text/csv", key=key)


def render_simple_table(df: pd.DataFrame, height: int = 300, key: str = "t") -> None:
    if df.empty:
        st.info("Sin datos.")
        return
    st.dataframe(df, hide_index=True, height=height, key=key)