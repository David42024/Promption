# 🛡️ Prompt Injection Filter — Sistema de detección en dos capas

Sistema académico de prueba de concepto para detectar **Prompt Injection** en aplicaciones web con LLMs. Combina dos capas de defensa:

| Capa | Técnica | Velocidad |
|------|---------|-----------|
| 1 · Heurística | Reglas regex configurables (`config/heuristics.yaml`) | < 1 ms |
| 2 · ML | Embeddings `all-MiniLM-L6-v2` + `RandomForestClassifier` | ~10-50 ms |

> **Explicación breve:** la primera capa detecta patrones conocidos (DAN, "ignora instrucciones", SQL Injection, exfiltración, etc.). La segunda capa aprende a distinguir intentos de inyección de prompts legítimos usando representaciones semánticas del texto. Un **filtro ensemble** (OR) combina ambas: si cualquiera de las dos capas bloquea, el prompt se rechaza antes de llegar al LLM.

## 🧩 Componentes

- **API FastAPI** (`src/api/`) — endpoints de filtrado, benchmark y monitorización.
- **Dashboard Streamlit** (`dashboard/`) — evaluación interactiva con 6 páginas y gráficas Plotly.
- **Benchmark** (`src/benchmark/`) — mide ASR (Attack Success Rate), precisión, recall, F1, FPR/FNR y latencia.
- **Entrenamiento** (`src/training/`) — pipeline de datos → embeddings → Random Forest.
- **LLM** (`src/llm/`) — cliente para Ollama (Llama 3 / Mistral), usado como "LLM vulnerable".

## 🚀 Puesta en marcha

### 1. Requisitos

- Python **3.10+** (probado con 3.11)
- [Ollama](https://ollama.com) en ejecución (opcional, pero recomendado para medir ASR real)
- ~500 MB de disco para los modelos de embeddings/LLM

### 2. Instalación

```bash
git clone <repo> && cd prompt-injection-filter
python -m venv .venv
# Windows:  .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dashboard.txt
```

### 3. Flujo completo (entrenar → benchmark → reporte → dashboard)

Cuatro comandos van desde cero hasta el dashboard:

```bash
# 1) Descargar los datasets públicos (NEPI, Shomi28, deepset, jailbreak_llms, OWASP)
python scripts/download_datasets.py

# 2) Preprocesar datos, entrenar el modelo y ejecutar el benchmark (ASR proxy, sin LLM)
python scripts/run_benchmark.py --no-llm

# 3) Generar el reporte con gráficas (Markdown + PDF estilizado)
python scripts/generate_report.py --pdf

# 4) Abrir el dashboard interactivo
streamlit run dashboard/app.py --server.port 8501
```

> `run_benchmark.py` automatiza las 3 fases: prepara `data/processed/training_data.csv`, entrena el Random Forest sobre los embeddings y guarda `models/random_forest.pkl`, y mide ASR / precisión / recall / F1 sobre todo el corpus. Salida en `data/results/`.

### 4. Benchmark con LLM real (Ollama)

```bash
python scripts/run_benchmark.py --no-train   # solo benchmark (modelo ya entrenado)
python scripts/run_benchmark.py              # completo + consultas a Ollama (más lento)
```

El `--no-llm` del paso 3 usa un **proxy determinista** (el ataque "tiene éxito" si no es bloqueado); con Ollama se mide el ASR real consultando a Mistral/Llama con el secreto `TOK-AZ9-KX7`.

### 5. Arrancar servidores

```bash
# Terminal 1 — API
uvicorn src.api.main:app --reload --port 8000

# Terminal 2 — Dashboard (si no se usó el paso 3)
streamlit run dashboard/app.py --server.port 8501
```

Abre **http://localhost:8501** y explora las 6 páginas. La API tiene Swagger interactivo en **http://localhost:8000/docs**.

### 6. Docker (opcional)

```bash
docker compose up --build          # api + dashboard (+ ollama opcional en el compose)
docker compose up -d ollama && docker exec -it pif-ollama ollama pull llama3.2
```

> Nota: los modelos y datos se montan como volúmenes; entrena el modelo *dentro* del contenedor o en el host antes de desplegar.

## 📊 Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/v1/filter` | Analiza un prompt (`{"text": "...", "use_ml": true}`) |
| POST | `/api/v1/filter/batch` | Análisis por lotes |
| POST | `/api/v1/benchmark` | Ejecuta un benchmark completo |
| GET | `/api/v1/benchmark/latest` | Últimos resultados en JSON |
| GET | `/api/v1/benchmark/history` | Historial de ejecuciones |
| GET | `/api/v1/metrics` | Métricas globales y por dataset |
| GET | `/api/v1/health` | Estado de API, Ollama y capas del filtro |
| GET | `/api/v1/model/features` | Feature importance del Random Forest |
| GET | `/api/v1/...` | (ver Swagger) |

## 📈 Páginas del dashboard

1. **Overview** — KPIs: ASR sin/con filtro, reducción, precisión/recall/F1, FPR/FNR, latencia.
2. **Benchmark Results** — tabla interactiva filtrável, matriz de confusión, ROC, ASR por ataque.
3. **Model Analysis** — feature importance, PCA de embeddings, correlaciones, análisis de errores, umbral ajustable.
4. **Real-Time Testing** — prueba interactiva del filtro + comparación con respuesta del LLM.
5. **Attack Analysis** — top payloads, patrones comunes, word clouds, distribuciones.
6. **System Health** — estado de Ollama/API, recursos, logs, configuración.

## 🧠 Cómo se calcula el ASR

El benchmark define un **código secreto** que el asistente jamás debe revelar. Cada payload malicioso intenta conseguir ese código:

- **ASR sin filtro:** % de intentos que logran que el LLM revele el secreto (o que no se niegue explícitamente — ASR "laxo").
- **ASR con filtro:** igual, pero los prompts bloqueados nunca llegan al LLM (cuentan como fallidos).
- **Sin Ollama:** se usa un proxy determinista (el ataque "tiene éxito" si no fue bloqueado), para que el flujo completo funcione sin GPU/internet.

## 🧪 Tests

```bash
python -m pytest tests/ -q
```

## 🗂️ Estructura

```
prompt-injection-filter/
├── src/
│   ├── api/        FastAPI (main, routes, models)
│   ├── filter/     Capas heurística, ML y ensemble
│   ├── training/   dataset, train, evaluate
│   ├── benchmark/  runner, payloads, metrics
│   ├── llm/        cliente Ollama
│   └── utils/      logger, config, visualizer
├── dashboard/      app.py + 6 páginas + components/ + utils/ + assets/
├── data/           raw/, processed/, results/
├── models/         random_forest.pkl
├── config/         config.yaml, heuristics.yaml
├── scripts/        download_datasets, run_benchmark, generate_report
├── tests/          test_heuristic, test_ml_filter, test_benchmark
├── Dockerfile · docker-compose.yml · .streamlit/config.toml
```

## 📄 Generar reporte

```bash
python scripts/generate_report.py --pdf
# -> reports/benchmark_report.md y .pdf
```

## 🔬 Notas para investigación

- Todas las métricas se guardan además en **JSON** (`benchmark_results_latest.json`) para reproducibilidad.
- El dashboard funciona **sin la API** leyendo directamente `data/results/` (la API solo se usa en Real-Time Testing si está disponible).
- Las reglas heurísticas son 100% configurables sin tocar código.
- Documentación de agentes IA: ver [`AGENTS.md`](AGENTS.md).