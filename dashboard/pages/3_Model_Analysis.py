"""Página 3 — Model Analysis: análisis profundo del modelo ML."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve()
while not (_ROOT / "src").exists() and _ROOT.parent != _ROOT:
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.decomposition import PCA
from sklearn.metrics import classification_report

from dashboard.components import charts
from dashboard.components.metrics import section_header
from dashboard.components.sidebar import setup_page
from dashboard.utils.data_loader import load_benchmark_results, load_history, load_model_metrics
from dashboard.utils.paths import MODELS_DIR
from dashboard.utils.theme import get_palette
from src.benchmark.metrics import all_metrics

setup_page("Model Analysis — Prompt Injection Filter", "🔬")

st.title("🔬 Model Analysis — Análisis del modelo ML")


@st.cache_resource(show_spinner="Cargando clasificador…")
def get_classifier_importance():
    import joblib
    path = str(MODELS_DIR / "random_forest.pkl")
    clf = joblib.load(path)
    imp = clf.feature_importances_
    dims = np.argsort(imp)[::-1][:30]
    return [{"dimension": f"dim_{i}", "importance": float(imp[i])} for i in dims]


@st.cache_resource(show_spinner="Cargando encoder de embeddings…")
def get_encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


df = load_benchmark_results()
model_metrics = load_model_metrics()

# ------------------------------------------------------------- feature import
section_header("Feature importance")
try:
    items = get_classifier_importance()
    charts.render_chart(charts.plot_feature_importance(items, top=20))
    if not model_metrics.empty:
        mrow = model_metrics.iloc[0]
        st.caption(f"Métricas del entrenamiento — Accuracy: {mrow.get('accuracy', 0):.3f} · "
                   f"Precision: {mrow.get('precision', 0):.3f} · Recall: {mrow.get('recall', 0):.3f} · "
                   f"F1: {mrow.get('f1', 0):.3f} · ROC-AUC: {mrow.get('roc_auc', 0):.3f}")
except FileNotFoundError:
    st.info("Modelo no entrenado todavía (falta models/random_forest.pkl). Ejecuta `python src/training/train.py`.")

# ------------------------------------------------------------- learning curve
section_header("Curva de aprendizaje (histórico)")
history = load_history()
if history:
    hdf = pd.DataFrame(history)
    fig = px.line(hdf.rename(columns={"timestamp": "Ejecución"}),
                  x="Ejecución", y=["asr_without", "asr_with"],
                  markers=True, labels={"value": "ASR", "variable": "Serie"})
    charts.apply_theme(fig, title="ASR a lo largo de las ejecuciones")
    charts.render_chart(fig)
else:
    st.info("No hay ejecuciones históricas guardadas todavía.")

# ------------------------------------------------------------- embeddings PCA
section_header("Distribución de embeddings (PCA)")
if not df.empty:
    try:
        n_pca = min(len(df), 1500)
        probe = df.sample(n=n_pca, random_state=42) if n_pca < len(df) else df
        encoder = get_encoder()
        with st.spinner("Calculando embeddings de los prompts del benchmark…"):
            emb = np.asarray(encoder.encode(probe["prompt"].tolist(), normalize_embeddings=True, batch_size=32),
                             dtype=np.float32)
        pca = PCA(n_components=2, random_state=42)
        coords = pca.fit_transform(emb)
        pca_df = pd.DataFrame({"PC1": coords[:, 0], "PC2": coords[:, 1],
                               "label": probe["label"].astype(int).map({1: "Malicioso", 0: "Benigno"})})
        pal = get_palette()
        fig = px.scatter(pca_df, x="PC1", y="PC2", color="label",
                         color_discrete_map={"Malicioso": pal["red"], "Benigno": pal["green"]},
                         opacity=0.75, labels={"PC1": f"PC1 ({pca.explained_variance_ratio_[0]:.1%})",
                                               "PC2": f"PC2 ({pca.explained_variance_ratio_[1]:.1%})"})
        charts.apply_theme(fig, title="Proyección PCA de los embeddings")
        charts.render_chart(fig)
        if n_pca < len(df):
            st.caption(f"PCA calculado sobre una muestra de {n_pca} de {len(df)} prompts "
                       "(submuestreo por rendimiento).")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"No se pudo calcular el PCA: {exc}")

# ------------------------------------------------------------- correlations
section_header("Matriz de correlación de características")
if not df.empty:
    num = df.select_dtypes(include=[np.number])
    keep = [c for c in ["heuristic_score", "ml_probability", "ensemble_score", "filter_latency_ms",
                        "llm_success_no_filter", "llm_success_with_filter"] if c in num.columns]
    corr = num[keep].corr().round(2)
    fig = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                    title="Correlación entre características")
    charts.apply_theme(fig)
    charts.render_chart(fig)

# ------------------------------------------------------------- threshold sim
section_header("Umbral de confianza ajustable")
thr = st.slider("Umbral del score ensemble para considerar bloqueo", 0.0, 1.0, 0.5, 0.01)
sim = df.copy()
sim["filter_blocked"] = (pd.to_numeric(sim["ensemble_score"], errors="coerce").fillna(0) >= thr).astype(int)
sm = all_metrics(sim)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Precisión", f"{sm['precision']:.3f}")
c2.metric("Recall", f"{sm['recall']:.3f}")
c3.metric("F1", f"{sm['f1']:.3f}")
c4.metric("FPR", f"{sm['fpr']:.3f}")

# ------------------------------------------------------------- error analysis
section_header("Análisis de errores (prompts mal clasificados)")
if not df.empty:
    err = df[(df["label"].astype(int) != df["filter_blocked"].astype(int))]
    if err.empty:
        st.success("El filtro clasificó correctamente todos los prompts del benchmark.")
    else:
        st.warning(f"{len(err)} errores de clasificación encontrados.")
        show = err[["prompt", "dataset", "attack_type", "label", "ensemble_score", "filter_blocked",
                    "heuristic_score"]].copy()
        show["error"] = show.apply(
            lambda r: "Falso positivo (benigno bloqueado)" if r["label"] == 0 else "Falso negativo (atacó sin bloquear)",
            axis=1)
        show = show.rename(columns={"prompt": "Prompt", "dataset": "Dataset", "attack_type": "Tipo",
                                    "label": "Real", "ensemble_score": "Score", "filter_blocked": "Pred"})
        st.dataframe(show.drop(columns="heuristic_score"), hide_index=True)

# ------------------------------------------------------------- per-class report
section_header("Métricas detalladas por clase")
if not df.empty:
    y_true = df["label"].astype(int)
    y_pred = df["filter_blocked"].astype(int)
    report = pd.DataFrame(classification_report(y_true, y_pred, output_dict=True, zero_division=0)).T
    st.dataframe(report.round(3), hide_index=False)