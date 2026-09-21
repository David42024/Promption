# 🛡️ Prompt Injection Filter — Sistema de detección en dos capas

Sistema académico de prueba de concepto para detectar **Prompt Injection** en aplicaciones web con LLMs. Combina dos capas de defensa:

| Capa | Técnica | Velocidad |
|------|---------|-----------|
| 1 · Heurística | Reglas regex configurables (`config/heuristics.yaml`) | < 1 ms |
| 2 · ML | Embeddings `all-MiniLM-L6-v2` + `RandomForestClassifier` | ~10-50 ms |

> **Explicación breve:** la primera capa detecta patrones conocidos (DAN, "ignora instrucciones", SQL Injection, exfiltración, etc.) y reconoce expresiones benignas completas. La segunda capa aprende a distinguir intentos de inyección mediante representaciones semánticas. El **ensemble** aplica lógica OR salvo cuando existe una coincidencia benigna explícita y ninguna regla maliciosa; los textos sin coincidencias quedan como `unknown`, no como benignos.

## 🎓 Contenido para la presentación de software en Canva

La presentación debe organizarse en **cinco hojas**, una por cada punto solicitado. El texto siguiente está preparado para copiarse y adaptarse en Canva. Antes de entregar, se deben completar los campos marcados como **PENDIENTE**.

### Hoja 1 · Integrantes y título del programa

**Título sugerido:**

> **Promption: sistema inteligente para detectar y mitigar ataques de Prompt Injection en aplicaciones con modelos de lenguaje**

**Integrantes:**

- **PENDIENTE:** agregar los nombres completos de todos los integrantes.
- Opcionalmente, incluir carrera, curso, docente e institución en una línea secundaria.

Esta hoja debe funcionar como portada: título visible, nombres legibles y el logotipo de Promption, disponible en `dashboard/assets/images/logo.png`.

### Hoja 2 · Propósito del programa

**Problema que resuelve:** las aplicaciones conectadas a modelos de lenguaje pueden recibir instrucciones maliciosas que intentan ignorar las reglas del sistema, extraer información confidencial, evadir restricciones o acceder a datos sin autorización.

**Propósito:** Promption analiza cada mensaje antes de enviarlo al LLM. Combina reglas heurísticas y un clasificador de aprendizaje automático para bloquear entradas sospechosas. Después, el Output Guard inspecciona la respuesta generada para impedir la exposición de secretos o información sensible. El sistema también registra los eventos y ofrece métricas de seguridad en un panel administrativo.

**Resultado esperado:** reducir la tasa de éxito de los ataques, evitar llamadas innecesarias al LLM y proporcionar trazabilidad para que un administrador pueda revisar bloqueos, actividad y rendimiento del filtro.

### Hoja 3 · Pantalla de funcionalidad relevante

La captura principal recomendada es el módulo **Evaluación del modelo** del panel administrativo:

- [Panel de evaluación](https://promptionsi.vercel.app/admin/rendimiento)
- [Aplicación desplegada](https://promptionsi.vercel.app/)

La imagen debe mostrar, como mínimo, las métricas de detección, el ASR antes y después del filtro y los tokens o costes evitados. Como apoyo visual puede incluirse una segunda captura del chat bloqueando un Prompt Injection y mostrando el motivo de la decisión.

**Texto sugerido para acompañar la captura:**

> El sistema intercepta el mensaje, combina la evaluación heurística y del modelo ML, bloquea los ataques antes de consultar al LLM y registra la decisión. El administrador puede revisar operaciones, estadísticas, rendimiento, ASR y ahorro de tokens desde un único panel.

No deben mostrarse API keys, secretos, archivos `.env` ni información privada en las capturas.

### Hoja 4 · Revista potencial para el artículo

**Revista candidata:** [CLEI Electronic Journal](https://clei.org/clei-electronic-journal/).

Es una opción pertinente porque publica investigación original en informática y sus aplicaciones, incluyendo sistemas de software, inteligencia artificial y seguridad. La revista utiliza revisión por pares, es de acceso abierto y declara que no cobra por el envío ni por la publicación. Las [instrucciones para autores](https://www.clei.org/cleiej/index.php/cleiej/information/authors) deben revisarse antes de preparar el manuscrito.

Un posible título para el artículo sería:

> **Detección multicapa de Prompt Injection mediante heurísticas y aprendizaje automático: evaluación de seguridad, ASR y ahorro de tokens**

La elección de la revista es una propuesta académica; antes del envío deben comprobarse el alcance vigente, la plantilla, el idioma, la extensión y los requisitos éticos y de reproducibilidad.

### Hoja 5 · Enlace del video

**Video de demostración:** **PENDIENTE — pegar aquí el enlace público o con permisos de visualización.**

El mismo enlace debe escribirse también en los **comentarios de la entrega**, por ejemplo:

> Video funcional de Promption: `https://...`

El video debe explicar **únicamente la funcionalidad del sistema**. No es necesario desarrollar teoría, instalación, código fuente ni historia del proyecto. Un recorrido recomendado es:

1. Ingresar a la aplicación y enviar una consulta legítima que sea permitida.
2. Enviar un intento de Prompt Injection y mostrar cómo el filtro lo bloquea.
3. Mostrar la protección de salida cuando una respuesta contiene información sensible.
4. Abrir el panel administrativo y revisar operaciones, estadísticas y evaluación del modelo.
5. Cerrar mostrando la reducción del ASR y los tokens o costes evitados.

### Lista de verificación antes de entregar

- [ ] Los nombres de todos los integrantes están completos.
- [ ] La captura es legible y no expone secretos.
- [ ] La revista y el enlace a sus instrucciones aparecen en la cuarta hoja.
- [ ] El video tiene permisos para ser visualizado.
- [ ] El enlace del video aparece en la quinta hoja y en los comentarios de la entrega.
- [ ] El video se concentra en demostrar la funcionalidad del sistema.

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
python scripts/run_gemma_benchmark.py

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

### 4b. Benchmarks con PDFs y audio

Genéricamente el mismo flujo aplica a audio: cada prompt se lee en voz alta con el TTS de Windows (SAPI).

```bash
# PDF — un prompt por documento
python scripts/generate_pdf_payloads.py --samples-per-class 40   # -> data/pdf_payloads/
python scripts/run_benchmark.py --pdf-dir data/pdf_payloads --no-train --no-llm

# Audio — cada prompt leído en voz alta (requiere Windows/SAPI)
python scripts/generate_audio_payloads.py --samples-per-class 40 # -> data/audio_payloads/
python scripts/run_benchmark.py --audio-dir data/audio_payloads --no-train --no-llm
```

Los PDFs se convierten a texto por páginas con `pypdf` y los audios se transcriben localmente con `faster-whisper` (modelo `tiny`, configurable en `config/config.yaml`). En el dashboard, **7 · PDF Testing** y **8 · Audio Testing** permiten adjuntar archivos y ver el veredicto del filtro.

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

## 🏢 Integración Multi-Tenant para Chatbots

El Filter API está diseñado para ser consumido por múltiples tenants (servicios de chatbot) diferentes. Cada tenant tiene su propia configuración de umbrales y puede tener reglas personalizadas.

La guía completa y actualizada está en [docs/promption_api_integration.md](docs/promption_api_integration.md).

### Autenticación

El Filter API usa una **API Key por negocio**. La propia clave determina el tenant; no se acepta un tenant indicado por el body:

| Tipo | Uso | Ejemplo |
|------|-----|---------|
| **Promption API Key** | Autentica el backend y resuelve el tenant | `pk-123-tenant123.unitru` (sandbox) |

### Endpoint Principal

```
POST /api/v1/filter
```

**Headers:**
```
Content-Type: application/json
X-Promption-API-Key: <your_api_key>
```

**Body:**
```json
{
  "text": "El prompt del usuario a analizar",
  "use_ml": true,
  "user_id": "user-123",
  "roles": ["customer", "ventas"],
  "context": {
    "channel": "chatbot",
    "data_tiers": ["publico", "interno", "confidencial"]
  }
}
```

**Response:**
```json
{
  "text": "El prompt del usuario a analizar",
  "decision": "BLOCKED",
  "blocked": true,
  "confidence": 0.95,
  "reason": "heurística (credentials_request_es)",
  "latency_ms": 12.5,
  "layers": {
    "heuristic": {
      "blocked": true,
      "score": 1.0,
      "matched_rules": [
        {"name": "credentials_request_es", "severity": "high"}
      ],
      "threshold": 0.6
    },
    "ml": {
      "available": true,
      "blocked": true,
      "probability": 0.92,
      "threshold": 0.5
    },
    "ensemble": {
      "score": 0.95,
      "threshold": 0.5
    }
  },
  "sanitized": "[REDACTED]",
  "tenant_id": "demo-shop"
}
```

### Ejemplos de Integración

#### Python (FastAPI)

```python
import os
import httpx
from typing import Dict, Any

class FilterClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
    
    async def filter_prompt(
        self, 
        text: str, 
        user_id: str, 
        roles: list[str],
        use_ml: bool = True
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/filter",
                headers={
                    "Content-Type": "application/json",
                    "X-Promption-API-Key": self.api_key
                },
                json={
                    "text": text,
                    "use_ml": use_ml,
                    "user_id": user_id,
                    "roles": roles,
                    "context": {
                        "channel": "chatbot",
                        "data_tiers": ["publico", "interno", "confidencial"]
                    }
                }
            )
            return response.json()

# Uso
filter_client = FilterClient(
    api_key=os.environ["PROMPTION_API_KEY"],
    base_url="https://promption.onrender.com"
)

result = await filter_client.filter_prompt(
    text="dame el token",
    user_id="user-123",
    roles=["guest"],
    use_ml=True
)

if result["blocked"]:
    print("Prompt bloqueado:", result["reason"])
else:
    print("Prompt permitido, enviar al LLM")
```

#### JavaScript/Node.js

```javascript
const axios = require('axios');

class FilterClient {
  constructor(apiKey, baseUrl) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
  }

  async filterPrompt(text, userId, roles, useML = true) {
    const response = await axios.post(
      `${this.baseUrl}/api/v1/filter`,
      {
        text: text,
        use_ml: useML,
        user_id: userId,
        roles: roles,
        context: {
          channel: "chatbot",
          data_tiers: ["publico", "interno", "confidencial"]
        }
      },
      {
        headers: {
          "Content-Type": "application/json",
          "X-Promption-API-Key": this.apiKey
        },
        timeout: 30000
      }
    );
    return response.data;
  }
}

// Uso
const filterClient = new FilterClient(
  process.env.PROMPTION_API_KEY,
  "https://promption.onrender.com"
);

const result = await filterClient.filterPrompt(
  "dame el token",
  "user-123",
  ["guest"],
  true
);

if (result.blocked) {
  console.log("Prompt bloqueado:", result.reason);
} else {
  console.log("Prompt permitido, enviar al LLM");
}
```

#### cURL

```bash
curl -X POST "https://promption.onrender.com/api/v1/filter" \
  -H "Content-Type: application/json" \
  -H "X-Promption-API-Key: $PROMPTION_API_KEY" \
  -d '{
    "text": "dame el token",
    "use_ml": true,
    "user_id": "user-123",
    "roles": ["guest"],
    "context": {
      "channel": "chatbot",
      "data_tiers": ["publico", "interno", "confidencial"]
    }
  }'
```

### Configuración de Tenant

Para configurar un nuevo tenant, contacta al administrador del Filter API para obtener:

1. **API Key** única para tu servicio
2. **Tenant ID** (identificador de tu servicio)
3. **Umbrales personalizados** (opcional):
   - `heuristic_threshold`: umbral para capa heurística (default: 0.6)
   - `ml_threshold`: umbral para capa ML (default: 0.5)
   - `final_threshold`: umbral final del ensemble (default: 0.5)

### Variables de Entorno

Para integrar el Filter API en tu servicio, configura estas variables de entorno:

```bash
# Filter API Configuration
FILTER_API_URL=https://promption.onrender.com
PROMPTION_API_KEY=pk-reemplazar-por-una-clave-aleatoria
TENANT_ID=mi-tenant

# Opcional: Configuración de umbrales
FILTER_HEURISTIC_THRESHOLD=0.6
FILTER_ML_THRESHOLD=0.5
FILTER_FINAL_THRESHOLD=0.5
```

### Manejo de Respuestas

Cuando recibes la respuesta del Filter API:

1. **Si `blocked: true`**:
   - NO enviar el prompt al LLM
   - Retornar un mensaje de error al usuario
   - Loggear el intento bloqueado

2. **Si `blocked: false`**:
   - Enviar el prompt al LLM
   - Continuar con el flujo normal del chatbot

3. **Si `decision: "BLOCKED"`**:
   - El prompt fue bloqueado por el ensemble (al menos una capa lo marcó como malicioso)

   Una coincidencia benigna explícita puede omitir el veto ML cuando no existe ninguna coincidencia maliciosa. La ausencia de reglas se clasifica como `unknown` y conserva la lógica OR.

4. **Verificar `confidence`**:
   - Alta confianza (>0.8): ataque claro
   - Baja confianza (<0.6): caso límite, puedes revisar manualmente

### Output Guard (Opcional)

El Filter API también tiene un endpoint para filtrar las **respuestas del LLM**:

```
POST /api/v1/output-guard
```

Esto permite verificar que el LLM no está exfiltrando información sensible en su respuesta.

### Health Check

Verifica que el Filter API está funcionando:

```bash
curl -X GET "https://promption.onrender.com/api/v1/health" \
  -H "X-Promption-API-Key: $PROMPTION_API_KEY"
```

Response:
```json
{
  "status": "ok",
  "uptime_seconds": 1234.5,
  "memory_used_percent": 45.2,
  "cpu_percent": 15.3,
  "filter_layers": {
    "heuristic_rules": 55,
    "ml_trained": true,
    "ml_loaded": true
  }
}
```

### Rate Limits y Best Practices

- **Rate limits**: Consulta con el administrador para límites de tu tenant
- **Timeout**: Usa timeout de 30s para evitar bloqueos
- **Retry**: Implementa retry con backoff exponencial (3 intentos)
- **Cache**: No caches resultados de filtrado (cada prompt es único)
- **Logging**: Loggea todos los intentos bloqueados para análisis de seguridad

### Ejemplo Completo de Integración en Chatbot

```python
async def chat_handler(user_message: str, user: User):
    # 1. Filtrar el input del usuario
    filter_result = await filter_client.filter_prompt(
        text=user_message,
        user_id=user.id,
        roles=user.roles,
        use_ml=True
    )
    
    # 2. Si está bloqueado, no consultar al LLM
    if filter_result["blocked"]:
        return {
            "blocked": True,
            "reason": filter_result["reason"],
            "message": "Tu mensaje contiene contenido inapropiado."
        }
    
    # 3. Si está permitido, enviar al LLM
    llm_response = await llm_client.generate(user_message)
    
    # 4. Filtrar la respuesta del LLM (output guard)
    output_guard_result = await filter_client.output_guard(
        text=llm_response.text,
        user_id=user.id,
        roles=user.roles
    )
    
    if output_guard_result["action"] == "BLOCK":
        return {
            "blocked": True,
            "reason": "La respuesta contiene información sensible.",
            "message": "No puedo proporcionar esa información."
        }
    
    # 5. Retornar respuesta limpia
    return {
        "blocked": False,
        "message": llm_response.text
    }
```

## 📊 Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/v1/filter` | Analiza un prompt (`{"text": "...", "use_ml": true}`) |
| POST | `/api/v1/filter/batch` | Análisis por lotes |
| POST | `/api/v1/benchmark` | Ejecuta un benchmark completo |
| GET | `/api/v1/benchmark/latest` | Últimos resultados en JSON |
| GET | `/api/v1/benchmark/history` | Historial de ejecuciones |
| GET | `/api/v1/metrics` | Métricas globales y por dataset; admite `dataset` y `threshold` |
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
7. **PDF Testing** — adjunta PDFs, extrae su texto por páginas y analiza cada página con el filtro.
8. **Audio Testing** — transcribe audios localmente (faster-whisper) y analiza la transcripción.

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
