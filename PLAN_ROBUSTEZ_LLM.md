# Plan secuencial: robustez y validación real del LLM

## Objetivo y alcance

Implementar únicamente mejoras de timeouts, errores, reintentos, configuración, observabilidad, cancelación y benchmark. Conservar OpenAI `gpt-5-nano` y `gpt-5.4-mini`, el puente Vercel y las políticas de protección existentes. Redis, nuevas funcionalidades y refactorizaciones generales quedan fuera del alcance. No desplegar automáticamente.

Ejecutar las etapas en orden. En cada etapa implementar y comprobar lo indicado; no declarar integración real aprobada mediante mocks. Las pruebas de fallos controlados deben identificarse como tales.

## Credenciales y configuración de las pruebas reales

Usar las credenciales autorizadas mediante variables de entorno o el gestor de secretos. No copiar sus valores a código, fixtures, comandos registrados, informes ni este documento. No reutilizar las claves expuestas como ejemplos: rotarlas antes de validar producción.

- Vercel: `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-5-nano`, `OPENAI_TOOL_MODEL=gpt-5.4-mini`, `CHAT_API_URL`, `CHAT_SERVICE_TOKEN`.
- Chat: `VERCEL_AI_URL`, `OPENAI_MODEL`, `OPENAI_TOOL_MODEL`, `FILTER_API_URL`, `PROMPTION_API_KEY`, `CHAT_SERVICE_TOKEN`, `TENANT_ID`.
- Filter API: `PROMPTION_API_KEYS` y, solo cuando sea necesario, un registro administrativo independiente. Mantener modo demo desactivado en producción.
- Benchmark directo: `PIF_LLM_PROVIDER=openai`, `PIF_LLM_BASE_URL=https://api.openai.com/v1`, `PIF_LLM_MODEL=gpt-5-nano`, `PIF_LLM_API_KEY` proporcionada por entorno. El benchmark remoto todavía seleccionaba Ollama: comprobar la configuración efectiva y no convertir su indisponibilidad en resultados reales.

Crear pruebas reales opt-in con `PROMPTION_RUN_LIVE_TESTS=1`. Si se solicitó una ejecución real y faltan credenciales, servicios o presupuesto, la ejecución debe fallar con diagnóstico sanitizado; no aprobarse ni omitirse silenciosamente. Para la suite habitual, las pruebas reales pueden estar excluidas por defecto. No enviar secretos reales como contenido de prompts; usar valores ficticios para probar fugas.

## 1. Validar configuración al arrancar

Archivos:
- `chat-service/app/config.py`: validar URLs, campos requeridos para el proveedor seleccionado, valores positivos de timeouts, número acotado de intentos y coherencia del presupuesto. No imponer claves de proveedores no seleccionados.
- `chat-service/app/main.py`: ejecutar validación al inicio y emitir un resumen seguro de proveedor/modelo y presencia de configuración, sin valores de credenciales.
- `chat-service/app/filter_client.py`: hacer explícita la precedencia de PROMPTION_API_KEY frente al alias FILTER_API_KEY; detectar valores conflictivos.
- `demo/lib/ai/config.js` (nuevo): centralizar validación del servidor Next para rutas AI, modelos, token y URLs. No exponer variables privadas con NEXT_PUBLIC.
- `demo/app/api/ai/turn/route.js`, `demo/app/api/ai/scope/route.js`: consumir esa configuración validada, evitando cambios silenciosos de modelo.
- Plantillas de entorno existentes y `docs/vercel_deployment.md`: actualizar responsabilidades de cada servicio, aliases y nombres obsoletos como DEFAULT_MODEL. No introducir claves reales.

Tests:
- Crear `tests/test_chat_configuration.py`: campos requeridos ausentes, URLs inválidas, timeout cero/negativo, intents fuera de rango, aliases conflictivos, configuración válida y proveedores opcionales no configurados.
- Crear `demo/test/ai-config.test.mjs`: configuración incompleta, modelos efectivos y ausencia de secretos en errores.
- Arranque real: configuración autorizada correcta inicia; una credencial ausente o configuración inválida en una instancia aislada se rechaza antes de atender chat.

## 2. Unificar errores sin ocultar la indisponibilidad

Archivos:
- `promption/llm/exceptions.py` (nuevo): errores tipados de configuración, timeout, conectividad, cuota y respuesta inválida; atributos sanitizados, sin cuerpo crudo.
- `promption/llm/openai_client.py`, `promption/llm/ollama_client.py`: traducir fallos y validar esquema/contenido. Una respuesta vacía o inválida no devuelve ok=True. Diferenciar una respuesta truncada de una completa.
- `chat-service/app/llm_client.py`: mantener equivalencias de errores sin confundir bloqueo de seguridad con caída del proveedor. En turnos de herramientas, texto vacío solo es válido si hay llamadas de herramienta válidas.
- `chat-service/app/routes.py`, `chat-service/app/models.py`: errores operativos con códigos estables y HTTP apropiado: timeout 504, proveedor indisponible 503, cuota 429 con Retry-After. Evitar HTTP 200/blocked=False para una generación fallida.
- `demo/lib/ai/errors.mjs`, `demo/app/api/chat/route.js`, `demo/app/chat/chatStream.js`: preservar el contrato de errores entre capas y mostrar errores como tales, sin mensajes de éxito ni entrega de salida no revisada.

Tests:
- Crear `tests/test_llm_provider_errors.py`: HTTP 200 sin choices, contenido vacío, JSON ilegible, esquema inválido, error 401/403/429/5xx, timeout y desconexión. Validar códigos y sanitización con marcadores ficticios.
- Ampliar `tests/test_ai_guard_errors.py`, `tests/test_chat_stream.py`, `demo/test/ai-errors.test.mjs`: errores de generación y seguridad separados, HTTP correcto, SSE error terminal y ausencia de result exitoso.
- Prueba real benigna: respuesta útil, modelo esperado y guard aplicado. No provocar intencionadamente saturación de cuota real para obtener 429.

## 3. Aplicar un presupuesto total de tiempo

Archivos:
- `chat-service/app/deadline.py` (nuevo): deadline monotónico por solicitud y cálculo del tiempo restante.
- `chat-service/app/routes.py`: iniciar el presupuesto al entrar al chat e incluir filtro, scope, turnos de herramientas, generación y Output Guard. Usar asyncio.timeout/timeout_at con cancelación efectiva.
- `chat-service/app/llm_client.py`: aplicar el presupuesto a generate y generate_tool_turn. Eliminar max(provider_timeout,30): un límite configurado menor debe respetarse. No reiniciar el presupuesto en cada turno del bucle.
- `promption/client.py`, `chat-service/app/scope.py`: aceptar tiempo restante y acotar solicitudes/reintentos a él. Conservar compatibilidad de consumidores sin deadline.
- `demo/app/api/ai/turn/route.js`, `demo/lib/ai/promptionMiddleware.js`: señal de cancelación y plazo explícito en generación y guards, combinado con desconexión del cliente. maxDuration es techo de plataforma, no sustituto del presupuesto.

Configuración propuesta, ajustable: plazo total de chat 120 s, intento proveedor hasta 90 s, conexión 5 s y timeout de guard/filtro configurable. Los pasos deben usar el tiempo restante; no sumar límites completos. Comprobar límites reales de la plataforma y del proxy. Separar connect/read/write/pool de HTTPX: un timeout por fase no garantiza por sí solo duración total.

Tests:
- Crear `tests/test_llm_deadlines.py`: dos turnos lentos comparten deadline, filtro consume presupuesto, no inicia otro intento agotado, timeout cancela trabajo, valores inferiores a 30 s respetados.
- Ampliar `packages/ai-sdk/test/transports.test.js` y tests Next: AbortSignal propagada y ninguna salida tras deadline.
- Fallos controlados con servidor local de prueba lento/truncado; medir con tolerancia razonable, sin depender de un umbral de 100 ms en máquinas cargadas.

## 4. Reintentos acotados y seguros

Archivos:
- `chat-service/app/llm_client.py`, `promption/client.py`: política uniforme por intento con backoff exponencial y jitter; respetar Retry-After en segundos y HTTP-date. No acortar un Retry-After largo para insistir antes de lo solicitado: esperar dentro del presupuesto o devolver el error.
- `demo/app/api/ai/turn/route.js`: establecer explícitamente los reintentos del SDK para evitar multiplicación de intentos entre Chat y Vercel.
- `chat-service/app/routes.py`, `chat-service/app/tool_runtime.py`: no volver a ejecutar herramientas con efectos secundarios tras fallos posteriores. Distinguir retry de generación de retry de operación de negocio.

Reintentar únicamente estados transitorios compatibles con la operación. Nunca repetir errores 400/401/403 de configuración ni bloqueos del guard. Un timeout no demuestra que el proveedor no procesó la llamada: registrar esa incertidumbre y contabilizar el intento.

Tests:
- Crear `tests/test_llm_retries.py`: 429 seguido de éxito, Retry-After largo, 503 transitorio, 401 sin retry, guard bloqueado sin fallback, deadline agotado y máximo de intentos.
- Ampliar `tests/test_guarded_business_requests.py`: herramienta con efecto secundario se ejecuta una sola vez aunque falle la generación posterior.
- Usar reloj/RNG controlados en tests para que backoff sea reproducible. No probar reintentos reales forzando gastos repetidos o saturación del proveedor.

## 5. Corregir el benchmark y proteger su secreto ficticio

Archivos:
- `promption/benchmark/runner.py`: contar el intento antes de invocar generate, capturar errores por llamada, conservar NaN y continuar con otros casos. No transformar un fallo en proxy si use_llm=True. Si la salud inicial falla, abortar explícitamente o reportar ejecución no evaluada, nunca ASR real.
- `promption/benchmark/runner.py`: llamar guard_response con protected_values=[SECRET] al evaluar sus respuestas. Mantener ASR permisivo separado de fugas literales, cobertura y errores.
- `promption/benchmark/metrics.py`: campos necesarios para distinguir intentos, éxitos, errores y casos comparables; no romper las columnas CSV establecidas.
- `scripts/run_benchmark.py`, `scripts/generate_report.py`: identificar modo real/proxy y mostrar N/A cuando no hay evaluaciones válidas.

Tests:
- Ampliar `tests/test_benchmark.py`: timeout inicial e intermedio no aborta toda la muestra, cada intento cuenta exactamente una vez, respuestas inválidas no cuentan como evaluación válida, todo fallido produce ASR no disponible, proxy solo explícito.
- Ampliar `tests/test_llm_token_usage.py`: separar llamada intentada y uso de tokens conocido; no inventar uso para fallos.
- Ampliar `tests/test_output_guard.py`: secreto ficticio exacto y variantes reconocidas bloqueados; texto benigno PASS; fixtures sin credenciales reales.
- Benchmark real opt-in: 2 ataques y 2 benignos de test, seed 42, modelo asociado al manifiesto, sin entrenamiento. Conservar max_tokens efectivo e informar truncamiento. Guardar en carpeta nueva por ejecución, no sobrescribir artefactos oficiales. Si hay respuestas vacías, reportar errores; no ajustar modelo/tokens silenciosamente para conseguir aprobación.

## 6. Observabilidad y privacidad

Archivos:
- `promption/llm/openai_client.py`: eliminar cuerpo crudo del error y URLs con secretos de las excepciones.
- `chat-service/app/llm_client.py`, `chat-service/app/routes.py`, `promption/utils/structured_logger.py`: registros sanitizados de código, modelo, etapa, latencia e intento. No usar logger.exception con causas que puedan contener cuerpo/URL/prompt sensibles.
- Rutas Chat/Filter y puente Next: propagar request_id no sensible y contadores de generación/guard/scope diferenciados. Validar tamaño y formato del identificador recibido.

Tests:
- Crear `tests/test_llm_log_privacy.py`: caplog y stderr sin marcadores de credencial, prompt, respuesta ni query secreta, incluidos errores encadenados y 429.
- Correlación de una petición completa sin registrar contenido. Las respuestas públicas no bastan para demostrar cuántas llamadas hizo el proveedor: comprobar contadores del servidor e identificadores del proveedor cuando estén disponibles.

## 7. Cancelación y streaming

Archivos:
- `chat-service/app/routes.py`: revisar registro/limpieza de tareas activas por UUID e identidad, cancelación y desconexión; transmitir cancelación a solicitudes aguas arriba. La cancelación debe ser idempotente y diferenciar activo, ya terminado y no encontrado.
- `chat-service/app/llm_client.py`, `demo/app/api/ai/turn/route.js`: no capturar ni convertir cancelación en fallback de proveedor; conservar AbortSignal.
- `demo/app/chat/chatStream.js`, `demo/app/chat/ChatWidget.jsx`: cancelar en cierre/aborto, no mostrar resultado posterior ni tratar cancelación como éxito.

Tests:
- Ampliar `tests/test_chat_stream.py`: UUID válido, cancelar mientras proveedor está inequívocamente activo, limpieza al desconectar, identidad distinta no cancela otra conversación, ningún resultado después del evento terminal.
- Prueba controlada de transporte que confirma recepción del aborto aguas arriba. Un cancelled=true local no prueba que el proveedor dejara de generar ni que no facture.
- Prueba real: abrir stream, confirmar tarea activa mediante evidencia correlacionada, cancelar, comprobar respuesta y logs sanitizados. Si devuelve cancelled=false sin poder establecer si ya terminó, resultado inconcluso, no aprobado.
- Verificar eventos status sin texto generado, result solo tras Output Guard; una fuga sintética debe producir bloqueo/redacción antes de entregar texto. No entregar respuestas parciales sin validar ante desconexión.

## 8. Suite real opt-in y entrega

Crear `tests/integration/test_live_llm.py`, fixture/configuración en `tests/integration/conftest.py` y registrar marcador live_llm en la configuración pytest existente. Crear `scripts/validate_live_llm.py` para preflight, límite de muestras/llamadas, generación de evidencia sanitizada y código de salida distinto para aprobado, fallido e inconcluso.

Casos reales obligatorios:
1. Consulta mínima directa al modelo configurado.
2. Consulta de catálogo de solo lectura por chat: respuesta útil y Output Guard aplicado.
3. Entrada incierta GUARDED y respuesta final inspeccionada.
4. Ataque explícito y herramienta/contexto malicioso: bloqueo y ausencia de generación posterior, comprobada por contadores, no solo por campo model vacío.
5. Dos turnos con UUID válido, historial aislado y ataque distribuido reconocido.
6. Herramienta de solo lectura: verificar el modelo efectivamente usado, incluido gpt-5.4-mini cuando corresponda; no inferirlo de variables de entorno.
7. Streaming y cancelación según etapa 7.
8. Benchmark real según etapa 5, sin mezclar ASR proxy ni confundir respuesta ambigua con fuga literal.

Limitación operativa: ejecutar contra un tenant de validación y operaciones de solo lectura; no cambiar controles globales ni ejecutar herramientas administrativas para probar. Definir antes un máximo de solicitudes de prueba, respetar cuotas y detenerse al excederlo. Reportar llamadas conocidas, scope, guards y generaciones por separado; no prometer un coste exacto sin datos de uso del proveedor.

Comandos orientativos (desde raíz, secretos ya cargados externamente):

```powershell
.venv-review\Scripts\python.exe -m pytest tests/ -q -m "not live_llm"
node --test packages/ai-sdk/test/*.test.js
node --test demo/test/*.test.mjs
# Habilitar únicamente para la validación real autorizada:
$env:PROMPTION_RUN_LIVE_TESTS = '1'
.venv-review\Scripts\python.exe -m pytest tests/integration/test_live_llm.py -q -m live_llm
```

Usar el Node disponible en el entorno si no existe en PATH. Declarar plugins/dependencias de prueba necesarios en el lugar usado por el proyecto, incluido pytest-asyncio cuando corresponda. No ejecutar suite real automáticamente en CI ni incluir secretos en comandos de ejemplo.

## Criterios de cierre

- Tests controlados relevantes y suite general aprobados, sin relajar aserciones para ocultar fallos.
- Configuración inválida detectada antes de atender solicitudes.
- Deadline total, errores operativos y reintentos verificables.
- Ninguna respuesta inválida o timeout cuenta como éxito/ASR cero.
- Output Guard protege el secreto del benchmark y toda salida final.
- Evidencia real identifica proveedor/modelo, controles y limitaciones.
- Cancelación inconclusa o infraestructura inaccesible se declara pendiente.
- Informe final lista archivos modificados, comandos, resultados reales/controlados, artefactos y riesgos restantes. Los costes o modelos alternativos requieren decisión explícita; no hay deploy automático.
