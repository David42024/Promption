# Validación en Producción (Deployed Validation)

Este documento describe la metodología, configuración y comandos para ejecutar la validación reproducible de **Promption** y **Chat Service** en sus entornos desplegados en producción mediante consultas reales al LLM.

> [!WARNING]
> **Aviso de Coste y Recursos**: La ejecución con `--execute` realiza peticiones reales contra los servicios remotos y modelos de lenguaje de producción (OpenAI). Cada consulta puede desencadenar múltiples llamadas al proveedor (evaluación de alcance, invocación de herramientas MCP, generación y Output Guard). Utilice el parámetro `--max-provider-calls` para controlar el presupuesto de inferencia.

---

## 1. Requisitos y Configuración de Credenciales

Las credenciales pueden configurarse directamente en el archivo privado `.env` (ignorado en `.gitignore`), o mediante variables de entorno en la sesión actual:

En **`.env`** (ignorado por git):
```env
VALIDATION_CHAT_TOKEN=chat_service_token
VALIDATION_FILTER_KEY=pk-123-tenant123.unitru
```

O en **PowerShell**:

```powershell
# Configuración de credenciales temporales en la sesión actual
$env:VALIDATION_CHAT_TOKEN = "<TU_CHAT_SERVICE_TOKEN>"
$env:VALIDATION_FILTER_KEY = "<TU_PROMPTION_API_KEY>"
```

También es posible suministrarlas como argumentos CLI opcionales: `--chat-token` y `--filter-key`.

### Endpoints por Defecto

El script utiliza las siguientes URLs predeterminadas (modificables mediante argumentos CLI):
- **Chat Service**: `https://chat-service-l31i.onrender.com/api/v1`
- **Filter API**: `https://promption.onrender.com/api/v1`
- **Demo Web**: `https://promptionsi.vercel.app`

---

## 2. Comandos de Ejecución (PowerShell)

### 1. Validar el corpus en dry-run (sin red ni consumo)
Verifica la sintaxis, esquema de casos, integridad de turnos y reproducibilidad de selección sin realizar llamadas externas:

```powershell
python scripts/run_deployed_validation.py --dry-run
```

### 2. Ejecutar una muestra de 5 casos secuencialmente
Ejecuta cinco casos respetando los grupos de conversación, con una pausa de 1 segundo entre solicitudes y un presupuesto máximo de 10 llamadas al proveedor:

```powershell
python scripts/run_deployed_validation.py --execute --limit 5 --delay 1.0 --max-provider-calls 10
```

### 3. Ejecutar el corpus completo
Ejecuta los 45 casos sintéticos del dataset con semilla fija para reproducibilidad y presupuesto de salvaguarda:

```powershell
python scripts/run_deployed_validation.py --execute --seed 42 --delay 1.0 --max-provider-calls 120
```

### 4. Ejecutar con comprobación de streaming SSE
Añade verificación del canal de streaming (`/chat/stream`), comprobando que no se liberen fragmentos de texto antes de la inspección de Output Guard y evaluando la cancelación limpia de generación:

```powershell
python scripts/run_deployed_validation.py --execute --limit 5 --include-streaming
```

### 5. Comparar dos ejecuciones
Compara la ejecución actual contra una ejecución anterior (referenciando el directorio del run previo o su archivo `benchmark.csv`), generando `comparison.csv`:

```powershell
python scripts/run_deployed_validation.py --execute --limit 10 --compare-with data/results/validation/production-scope-20261008-224314-e07106
```

---

## 3. Presupuesto de Llamadas y Semántica de Inferencia

El argumento `--max-provider-calls <N>` establece un límite superior sobre las llamadas observadas:
- Una única consulta de usuario puede requerir:
  1. Clasificación semántica de alcance (`scope_calls`).
  2. Llamada al LLM con selección de herramientas MCP.
  3. Llamada al LLM con el resultado de la herramienta inyectado (`generation_calls`).
- Por tanto, el número de llamadas internas no se conoce con exactitud hasta que el servicio responde. Cuando la suma acumulada de `provider_calls` alcanza o excede el presupuesto, el script **detiene inmediatamente la programación de nuevos casos**, preservando los artefactos completados hasta ese instante.
- Las **sondas de streaming (`--include-streaming`)** también respetan este presupuesto: si el presupuesto se ha alcanzado antes de iniciar el streaming, se omiten de forma segura; y si se ejecutan, sus llamadas se extraen del evento terminal (`execution_metrics.provider_calls`) y se computan tanto en el acumulador de presupuesto como en `reported_provider_calls` en `summary.json`.
- La opción `--concurrency <N>` permite paralelizar la ejecución de casos aislados manteniendo estrictamente secuenciales los turnos internos de cada grupo de conversación (`conversation_group`), con sincronización segura mediante cerrojos de hilo (`threading.RLock`).

---

## 4. Corpus de Validación (`data/validation/deployed_cases.jsonl`)

El dataset contiene 45 casos sintéticos equilibrados entre tres clases principales:
- **`benign`**: Consultas legítimas del catálogo público, especificaciones técnicas, traducciones de políticas públicas, definiciones conceptuales de stock y consultas administrativas/ventas con roles autorizados.
- **`policy`**: Peticiones que violan políticas de negocio o RBAC (clientes solicitando sueldos, stock interno con SKU o EBITDA), consultas ambiguas sin historial previo que requieren clarificación (`clarify`), o temas fuera de alcance (ecuaciones diferenciales, recetas).
- **`attack`**: Inyecciones de prompt directas e indirectas, suplantación de rol (`[SYSTEM]`, Developer Mode), delimitadores XML/Markdown, evasiones mediante codificación Base64 y ataques distribuidos en dos turnos.

### Grupos de Conversación (`conversation_group`)
- Los casos con `conversation_group` definido comparten la misma identidad sintética de usuario y el mismo `conversation_id`.
- Se ejecutan en su estricto orden de turnos original (por ejemplo, Turno 1 consulta de producto, Turno 2 solicitud de traducción de la respuesta anterior).
- Los casos aislados (`conversation_group: null`) se ejecutan con identidades y conversaciones independientes generadas por UUID.

---

## 5. Estructura de Artefactos Generados

Cada ejecución crea un directorio exclusivo en:
`data/results/validation/<run_id>/` (donde `<run_id>` sigue el formato `production-YYYYMMDD-HHMMSS-<hash>`).

Los artefactos producidos son:
1. **`benchmark.csv`**:
   - Conserva estrictamente las **21 columnas obligatorias** definidas en `AGENTS.md`:
     `id, prompt, dataset, attack_type, source, label, heuristic_score, heuristic_blocked, ml_probability, ml_blocked, ensemble_score, filter_blocked, filter_latency_ms, heuristic_latency_ms, ml_latency_ms, matched_rules, llm_success_no_filter, llm_success_with_filter, llm_latency_ms, response_no_filter, response_filtered`.
   - Incluye columnas extendidas con telemetría de producción: `expected_action, observed_action, actual_model, provider_calls, scope_calls, generation_calls, known_total_tokens, usage_complete, request_id`.
   - Las columnas `response_no_filter` y `llm_success_no_filter` se mantienen como `null` ya que no se ejecuta un baseline inseguro sin protección en producción.
   - **No sobrescribe** el archivo histórico oficial `data/results/benchmark_results.csv`.
2. **`evidence.jsonl`**: Registro completo sanitizado escrito de forma incremental tras cada caso. Si el proceso se interrumpe (Ctrl+C), los datos ya evaluados quedan intactos.
3. **`summary.json`**: Agregados cuantitativos, matrices de confusión por capa (TP, TN, FP, FN, FPR, FNR con denominadores explícitos), total de llamadas a proveedor (incluyendo streaming) y desglose de latencias globales vs. consultas con generación efectiva.
4. **`report.md`**: Informe legible en Markdown con la configuración efectiva (sin secretos), análisis de falsos positivos/negativos, cobertura de tokens y limitaciones.
5. **`comparison.csv`** (opcional): Tabla comparativa por `id` frente a una ejecución previa, identificando diferencias en bloqueo, llamadas, tokens y casos ausentes.

---

## 6. Pruebas Locales Automatizadas

Para validar el script sin realizar ninguna llamada a internet ni incurrir en costes:

```bash
python -m pytest tests/test_deployed_validation.py -v
```

La suite cubre 19 escenarios mediante `httpx.MockTransport`:
- Validación de CLI sin argumentos y modo dry-run.
- Exigencia estricta de credenciales en `--execute`.
- Validación de esquema e integridad del corpus JSONL.
- Conservación de turnos y orden en grupos de conversación.
- Aislamiento de sesiones entre casos independientes.
- Manejo de respuestas HTTP 401, 429 (captura de `Retry-After`), 500, timeouts y JSON inválido.
- Verificación de ausencia de reintentos automáticos en llamadas a `/chat`.
- Preservación de ceros (`provider_calls = 0`) frente a `null` en uso parcial de tokens.
- Coherencia de contadores (`provider_calls == scope_calls + generation_calls`).
- Matrices de confusión con capas omitidas y errores sin falsos positivos artificiales.
- Semántica de tres estados: `allow`, `block` y `clarify`.
- Verificación del flujo SSE en el nivel de estructura de datos (`frame.data.guard`) y detección de streams sin resultado validado.
- Sanitización de claves API y canarios (`TOK-AZ9-KX7`).
- Escritura incremental de evidencia ante excepciones.
- Creación de rutas únicas sin colisión con benchmarks oficiales.
- Detección de casos nuevos o faltantes en comparación.
- Detención automática de nuevas consultas al agotarse el presupuesto `--max-provider-calls`.
- Respeto del presupuesto en sondas de streaming y agregación de sus llamadas al total.
- Control de concurrencia `--concurrency` con conservación de orden en turnos y sincronización segura.
