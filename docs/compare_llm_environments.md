# Comparación de backend local e Incubunt con OpenAI

El script `scripts/compare_llm_environments.py` ejecuta el mismo corpus sintético de 45 casos en ambos escenarios. Incluye preguntas benignas, ataques, autorización, traducciones, comparaciones y conversaciones de varios turnos. No realiza llamadas sin `--execute`; `--dry-run` valida y estima el tiempo sin red.

## Preparación

Inicia localmente la Filter API, el Chat Service y, si tu cliente lo necesita, el bridge de Next.js. Configura el Chat Service local para usar sus servicios locales, no el bridge/filtro desplegados. Ambos entornos deben usar el mismo commit, modelos OpenAI, reglas, modelo ML, política de empresa, límites de tokens y timeouts. No se inicia ni reconfigura ningún servicio automáticamente.

Las URLs de chat y filtro deben incluir el prefijo `/api/v1`; las de demo son el origen del frontend. No asumimos que el dominio Incubunt aloja todos los backends: confirma sus rutas y conexiones internas antes de comparar infraestructura. El preflight verifica salud y que chat declare proveedores OpenAI conectados; no puede probar que todos los saltos sean locales ni que los commits sean idénticos. El manifiesto deja esa limitación explícita.

Desde PowerShell, en la raíz del repositorio, establece:

```powershell
$env:LOCAL_CHAT_URL = 'http://localhost:8001/api/v1'
$env:LOCAL_FILTER_URL = 'http://localhost:8000/api/v1'
$env:LOCAL_DEMO_URL = 'http://localhost:3000'
$env:INCUBUNT_CHAT_URL = '<URL_REAL_CHAT_INCUBUNT>/api/v1'
$env:INCUBUNT_FILTER_URL = '<URL_REAL_FILTRO_INCUBUNT>/api/v1'
$env:INCUBUNT_DEMO_URL = 'https://promption.incubunt.com'
$env:LOCAL_VALIDATION_CHAT_TOKEN = '<TOKEN_LOCAL>'
$env:LOCAL_VALIDATION_FILTER_KEY = '<CLAVE_LOCAL>'
$env:INCUBUNT_VALIDATION_CHAT_TOKEN = '<TOKEN_INCUBUNT>'
$env:INCUBUNT_VALIDATION_FILTER_KEY = '<CLAVE_INCUBUNT>'
```

Los puertos mostrados son ejemplos: usa los puertos reales. OPENAI_API_KEY se configura en los backends, no en el script. Las credenciales del validador solo se leen del entorno. Las peticiones reales consumen tokens.

## Ejecución

```powershell
# Validar sin red
.\.venv-review\Scripts\python.exe scripts/compare_llm_environments.py --dry-run

# Primera muestra, ambos escenarios
.\.venv-review\Scripts\python.exe scripts/compare_llm_environments.py --execute --limit 5 --max-provider-calls 30

# 45 casos por escenario, una repetición
.\.venv-review\Scripts\python.exe scripts/compare_llm_environments.py --execute --max-provider-calls 180

# Repetir tres veces: hasta 270 consultas al chat
.\.venv-review\Scripts\python.exe scripts/compare_llm_environments.py --execute --repeats 3 --max-provider-calls 180
```

El presupuesto es por escenario y repetición, basado en llamadas observadas. Puede recortar el corpus o excederse por las llamadas internas de una solicitud; las métricas no recibidas no establecen un límite de coste. Una consulta HTTP no equivale a una llamada OpenAI. No hay reintentos ni sondas de streaming, por sus limitaciones pendientes de métricas. La concurrencia es uno para evitar errores de tareas concurrentes ocultos en el validador existente y separar efectividad de saturación.

## Resultados

Cada ejecución crea un directorio único en `data/results/validation/environment-comparison-*`. Contiene manifiesto de corpus/semilla, resumen conjunto, CSV por caso para comparar escenarios, y subdirectorios con benchmark.csv, evidence.jsonl, report.md y scenario.json por escenario/repetición. Los modelos efectivos se conservan por caso: compara solamente ejecuciones con configuraciones equivalentes. El orden de los escenarios se alterna entre repeticiones.

Se reportan FP/FN por capa, decisiones finales, errores, llamadas, tokens conocidos y cobertura parcial. Hay p50/p95/p99 de solicitudes HTTP exitosas y de solicitudes con generación; los errores permanecen separados. Los percentiles con pocas muestras no certifican capacidad. ASR confidencial queda no evaluado sin canario protegido y comparación válida.

No se sobrescriben los artefactos oficiales. Se conserva evidencia incremental y se exportan los resultados parciales ante interrupción, cuando los datos permiten hacerlo. Si un escenario falla, la ejecución se detiene: corrige su configuración antes de continuar.

## Tiempo estimado

Con 6–12 segundos por caso (incluyendo sonda de filtro y chat), más 2 segundos de pausa: 5 casos por escenario requieren aproximadamente 1,3–2,3 minutos; 45 casos por escenario, 12–21 minutos; tres repeticiones completas, 36–63 minutos. Es una estimación, no una garantía: calentamiento, respuestas largas, colas, timeouts y presupuesto alteran la duración. No se mide aquí el tiempo de arranque de servicios. Las sesiones y el corpus quedan aislados por ejecución.

Pruebas locales, sin llamadas externas:

```powershell
.\.venv-review\Scripts\python.exe -m pytest tests/test_compare_llm_environments.py tests/test_deployed_validation.py -q
```
