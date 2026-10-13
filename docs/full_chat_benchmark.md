# Benchmark del recorrido completo

`compare_llm_environments.py` envía los mismos casos al Chat Service local y al remoto. El backend ejecuta filtro, historial, alcance, permisos, MCP y Output Guard cuando corresponde. No fuerza etapas que legítimamente se omiten. Las métricas del chat provienen de su respuesta real; la sonda adicional de Filter API se identifica por separado y consume cuota del filtro.

## Selección configurable y reproducible

```powershell
.\.venv-review\Scripts\python.exe scripts/compare_llm_environments.py --dry-run --messages 100 --seed 42 --kind-weights 50 40 10
.\.venv-review\Scripts\python.exe scripts/compare_llm_environments.py --dry-run --messages 5000 --seed 42 --kind-weights 60 30 10
```

`--messages` fija la cantidad exacta por entorno y repetición. `--kind-weights` indica los pesos de benignos, ataques y política/alcance; no garantiza cuotas exactas, pues las conversaciones se conservan completas. La selección aleatoria se hace por sesiones con reemplazo: las repeticiones se identifican con `seed_id`, `family_id` y `repetition`. El texto original se conserva para no cambiar la semántica de referencias e instrucciones de varios turnos. No presentar las repeticiones como 5.000 mensajes únicos o independientes. `--limit` mantiene el muestreo anterior sin expansión; es incompatible con `--messages`.

Para ejecutar, añadir `--execute`, las seis URLs explícitas `--local-chat-url`, `--local-filter-url`, `--local-demo-url`, `--incubunt-chat-url`, `--incubunt-filter-url`, `--incubunt-demo-url`, o sus variables `LOCAL_*_URL` e `INCUBUNT_*_URL`. Chat y filtro deben indicar su prefijo real, normalmente `/api/v1`. Credenciales en `LOCAL_VALIDATION_CHAT_TOKEN`, `LOCAL_VALIDATION_FILTER_KEY`, `INCUBUNT_VALIDATION_CHAT_TOKEN`, `INCUBUNT_VALIDATION_FILTER_KEY`. No usar un dominio de frontend como evidencia de que el backend corre allí.

```powershell
.\.venv-review\Scripts\python.exe scripts/compare_llm_environments.py --execute --messages 100 --seed 42 --kind-weights 50 40 10 --max-provider-calls 600
```

Ese presupuesto es por entorno y repetición, observado después de cada solicitud: una solicitud con herramientas puede excederlo. El valor predeterminado 180 puede detener una prueba grande antes de completarla. Ajustarlo tras un piloto, no asumir una llamada por mensaje.

## Evidencias y métricas

`selected_cases.jsonl` conserva exactamente el corpus usado. Cada escenario genera evidencia incremental, CSV, resumen y reporte. El CSV conserva las 21 columnas obligatorias y añade:

- Estado y latencia de `input_filter`, `conversation_guard`, `scope`, `generation`, `tools`, `output_guard`.
- Decisiones del filtro dentro del chat, separadas de las sondas independientes.
- Clasificación y motivo de alcance, modelo y comparación con `expected_scope` si el corpus lo declara.
- ID de conversación, índice de turno, familia y autenticación.
- Auditoría de herramientas permitidas/denegadas y comparación con `expected_tools` cuando esté etiquetado.
- Tokens, llamadas, completitud de uso, errores, decisión final y matrices FP/FN existentes.

`summary.json` incorpora `full_chat_stages`: estados por etapa, latencias p50/p95/p99, clases de alcance, discrepancias etiquetadas y auditorías MCP. Un permiso de herramienta no demuestra ejecución exitosa; una etapa no reportada permanece desconocida. No derivar FP/FN de alcance usando la etiqueta ataque: un ataque puede estar dentro del dominio empresarial. Añadir etiquetas `expected_scope` explícitas si se requiere esa matriz específica.

Este script cubre el recorrido protegido completo. **No activa un brazo sin protección ni deshabilita controles de producción.** La comparación sin protección del script `run_real_paired_benchmark.py` sigue siendo una ablación del núcleo, no del chat completo. Tampoco mide ASR confidencial estricto sin un canario controlado instalado en la fuente de conocimiento.

Estimación para ambos entornos, secuenciales: `2 × mensajes × (latencia media de chat + sonda de filtro + pausa)`. Con 5.000 por entorno y 8–18 segundos totales por caso: aproximadamente 22–50 horas. Un piloto de 50–100 casos debe reemplazar esa aproximación.
