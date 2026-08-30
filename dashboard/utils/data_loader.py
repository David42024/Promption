"""Data access layer for the dashboard.

Reads benchmark artifacts directly from disk (works without the FastAPI server)
and can optionally refresh live data through the API when it is reachable.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import requests

from dashboard.utils.paths import RESULTS_DIR, ROOT_DIR

API_URL = os.getenv("PIF_API_URL", "http://localhost:8000").rstrip("/")


# ------------------------------------------------------------------ file based
@st.cache_data(ttl=10, show_spinner=False)
def load_benchmark_results() -> pd.DataFrame:
    p = RESULTS_DIR / "benchmark_results.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, encoding="utf-8")


@st.cache_data(ttl=10, show_spinner=False)
def load_latest_json() -> dict:
    p = RESULTS_DIR / "benchmark_results_latest.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


@st.cache_data(ttl=10, show_spinner=False)
def load_model_metrics() -> pd.DataFrame:
    p = RESULTS_DIR / "model_metrics.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, encoding="utf-8")


@st.cache_data(ttl=10, show_spinner=False)
def load_history() -> list[dict]:
    hist = RESULTS_DIR / "history"
    if not hist.exists():
        return []
    runs = []
    for f in sorted(hist.glob("run_*.csv")):
        df = pd.read_csv(f)
        runs.append({
            "file": f.name,
            "rows": len(df),
            "asr_without": pd.to_numeric(df["llm_success_no_filter"], errors="coerce").mean(),
            "asr_with": pd.to_numeric(df["llm_success_with_filter"], errors="coerce").mean(),
            "timestamp": f.name.removeprefix("run_").removesuffix(".csv").replace("_", " "),
        })
    return runs


def latest_benchmark_timestamp() -> str:
    payload = load_latest_json()
    ts = payload.get("timestamp", "")
    if not ts:
        return "Sin ejecuciones todavía"
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


def file_exists(path: Path) -> bool:
    return path.exists()


# ---------------------------------------------------------------------- api
def api_reachable(timeout: float = 2.0) -> bool:
    try:
        r = requests.get(f"{API_URL}/api/v1/health", timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


@st.cache_data(ttl=10, show_spinner=False)
def api_health() -> dict:
    try:
        r = requests.get(f"{API_URL}/api/v1/health", timeout=3)
        return r.json() if r.status_code == 200 else {"status": "offline"}
    except requests.RequestException:
        return {"status": "offline"}


def api_filter(text: str, use_ml: bool = True, timeout: float = 60) -> dict | None:
    try:
        r = requests.post(f"{API_URL}/api/v1/filter", json={"text": text, "use_ml": use_ml}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        return None
    return None


def api_run_benchmark(sample_size: int | None = None, use_llm: bool = False, timeout: float = 600) -> dict | None:
    try:
        r = requests.post(f"{API_URL}/api/v1/benchmark",
                          json={"sample_size": sample_size, "use_llm": use_llm}, timeout=timeout)
        return r.json() if r.status_code == 200 else None
    except requests.RequestException:
        return None