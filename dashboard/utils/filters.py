"""Interactive filtering helpers for the dashboard."""
import pandas as pd
import streamlit as st


def dataset_options(df: pd.DataFrame) -> list[str]:
    if df.empty or "dataset" not in df.columns:
        return []
    return sorted(df["dataset"].dropna().unique().tolist())


def attack_type_options(df: pd.DataFrame) -> list[str]:
    if df.empty or "attack_type" not in df.columns:
        return []
    vals = df.loc[df["label"].astype(int) == 1, "attack_type"].dropna().unique()
    return sorted(vals.tolist())


@st.cache_data(ttl=5, show_spinner=False)
def filter_df(df: pd.DataFrame, datasets: list[str], decision: str, attack_success: str) -> pd.DataFrame:
    out = df.copy()
    if datasets:
        out = out[out["dataset"].isin(datasets)]
    if decision != "Todos":
        out = out[out["filter_blocked"].astype(int) == (1 if decision == "Bloqueado" else 0)]
    if attack_success != "Todos":
        col = "llm_success_with_filter"
        if col in out.columns:
            s = pd.to_numeric(out[col], errors="coerce")
            out = out[s == (1.0 if attack_success == "Engañó al LLM" else 0.0)]
    return out.reset_index(drop=True)


def sidebar_filters(df: pd.DataFrame, key_prefix: str = "bm") -> tuple[list[str], str, str]:
    datasets = dataset_options(df)
    ds = st.multiselect("Filtro por dataset", datasets, default=datasets if datasets else None, key=f"{key_prefix}_ds")
    decision = st.selectbox("Decisión del filtro", ["Todos", "Bloqueado", "Permitido"], key=f"{key_prefix}_dec")
    success = st.selectbox("Éxito del ataque", ["Todos", "Engañó al LLM", "No engañó"], key=f"{key_prefix}_suc")
    return ds, decision, success