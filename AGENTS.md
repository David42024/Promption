# AGENTS.md — Instrucciones para agentes de IA

Guía para trabajar en este repositorio (Proyecto académico: detección de Prompt Injection).

## Estructura esencial

- **`src/filter/`** — núcleo: `heuristic_filter.py` (regex, reglas en `config/heuristics.yaml`), `ml_filter.py` (SentenceTransformers `all-MiniLM-L6-v2` + `RandomForestClassifier`, singleton con carga lazy), `ensemble_filter.py` (orquesta capas, devuelve `EnsembleResult`).
- **`src/api/`** — FastAPI. Endpoints en `routes.py` (prefijo `/api/v1`). Pydantic en `models.py`.
- **`src/benchmark/`** — `runner.py` ejecuta el benchmark (mide ASR con un secreto `TOK-AZ9-KX7` que el LLM no debe revelar), `metrics.py` cálculos puros, `payloads.py` carga del dataset.
- **`src/training/`** — `dataset.py` (CSV raw → `data/processed/training_data.csv`), `train.py` (embeddings → RandomForest → `models/random_forest.pkl`).
- **`dashboard/`** — Streamlit multipágina. `app.py` + `pages/` (convención de nombres `1_.., 2_..`). Componentes reutilizables en `dashboard/components/` (Plotly), carga de datos en `dashboard/utils/data_loader.py`, filtro en proceso en `dashboard/utils/filter_runner.py`.
- **`config/`** — `config.yaml` (rutas, modelo, ensemble, llm) y `heuristics.yaml` (reglas regex). Cargar SIEMPRE vía `src/utils/config.py` (`load_config`, `load_heuristics`), que resuelve rutas absolutas respecto a la raíz.

## Convenciones y reglas

- **Python 3.10+**, sin comentarios salvo docstrings cuando aporten.
- No añadir dependencias sin justificarlas en `requirements.txt` (backend) o `requirements-dashboard.txt` (Streamlit).
- **Modelo completo tabulado en CSV** con estas columnas fijas (no renombrar en `runner.py`): `id, prompt, dataset, attack_type, source, label, heuristic_score, heuristic_blocked, ml_probability, ml_blocked, ensemble_score, filter_blocked, filter_latency_ms, heuristic_latency_ms, ml_latency_ms, matched_rules, llm_success_no_filter, llm_success_with_filter, llm_latency_ms, response_no_filter, response_filtered`.
- `dataset` en los CSV raw vale `OWASP | BIANCA | Jailbreak | GitHub | Custom | NEPI` (malicioso) o `Benigno` (legítimo). `scripts/download_datasets.py` mapea NEPI→`NEPI`, verazuo/jailbreak_llms→`Jailbreak`, Shomi28/deepset→`Custom`, payloads built-in→`OWASP`.
- El ensemble usa lógica **OR** (cualquier capa bloquea → bloqueado). Mantener esa propiedad de fail-safe.
- El ML está **optimizado para fallar solo** (`is_trained()` falso → no lanza).
- Streamlit: usar `@st.cache_data(ttl=…)` para datos y `@st.cache_resource` para modelos pesados. `st.cache_data.clear()` + `st.rerun()` para refrescar.

## Comandos útiles

```bash
python -m pytest tests/ -q                        # tests (heurística, ML, benchmark)
python src/training/train.py                      # entrenar modelo
python scripts/download_datasets.py               # descargar datasets públicos (NEPI, Shomi28, deepset, jailbreak_llms…)
python scripts/run_benchmark.py --no-llm          # benchmark rápido (sin Ollama)
uvicorn src.api.main:app --reload --port 8000     # API
streamlit run dashboard/app.py --server.port 8501 # dashboard
python scripts/generate_report.py --pdf           # reporte
```

## Verificación tras cambios

1. `python -m pytest tests/ -q` — todos verdes.
2. `python scripts/run_benchmark.py --no-llm` — genera `data/results/benchmark_results.csv` sin errores (necesita el modelo entrenado).
3. Arranque del dashboard en modo smoke: `streamlit run dashboard/app.py` sin excepciones de import.
4. La API: `uvicorn src.api.main:app` y `GET /api/v1/health` → 200.

## No hacer

- No meter secretos en el repo ni en logs (`.env`, claves, tokens).
- No escribir prompts/emails/URLs inventados como si fueran CDN oficiales; si se descargan payloads usar `scripts/download_datasets.py`.
- No mezclar lógica de Plotly (dashboard) con matplotlib (src/utils/visualizer.py se usa solo en scripts/reportes).