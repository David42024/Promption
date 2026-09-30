# Validación del chat y sus herramientas

## Pruebas locales

```bash
.venv/bin/python -m pytest tests/ -q
node --test packages/ai-sdk/test/*.test.js demo/test/*.test.mjs
npm --prefix packages/ai-sdk run test:types
```

`tests/test_guarded_business_requests.py` cubre stock con saludos, errores de
escritura, sin tildes, sinónimos, proveedores, cuatro roles y conversaciones con
historial de herramientas. Ejecuta los flujos con probabilidades ML bajas y medias,
MCP real local y un modelo de respuesta simulado para no consumir OpenAI.

También valida bloques del filtro, contexto incompleto, salida requerida pero
desactivada, alcance incierto, fallos del servicio, redacciones completas y
respuestas inválidas de Output Guard. Un documento no se crea si su contenido
no supera la revisión. Los roles sin sesión autenticada no conceden acceso interno.

Los tests existentes de `test_conversation_guard.py`, `test_scope.py` y el middleware
AI SDK conservan las regresiones de inyección acumulada, resultados de herramientas
no confiables, escalamiento de rol y herramientas fuera de alcance.

`test_chat_capabilities.py` comprueba preguntas sobre funciones y permisos,
incluido «dime qué puedes ahcer», con los cuatro roles. La descripción procede
del catálogo autorizado por el servidor y pasa por el filtro de contexto,
la revisión de alcance, Output Guard y ACL de salida. La app reconoce preguntas
completas de capacidades como una función pública sin depender de OpenAI para
esa decisión; no acepta solicitudes mixtas ni herramientas propuestas por esa vía. Las solicitudes mixtas
y el historial malicioso conservan sus bloqueos. El diagnóstico de `/ai/guard`
indica si se rechazó la entrada o la salida sin registrar su contenido.

## Pruebas de integración con modelos reales

Requieren los tres servicios locales activos y autorización del operador para
enviar las consultas y el contexto del bot a OpenAI. Este comando usa las cuentas
demo, crea conversaciones aisladas y realiza 32 mensajes en 30 casos:

```bash
.venv/bin/python scripts/validate_chat.py --live
```

La matriz está en `tests/fixtures/chat_cases.json`. Comprueba los tres mensajes de
la captura, variantes de inventario, descuentos, campañas, catálogo, visitantes,
permisos, intentos de inyección, solicitudes ajenas o mixtas, historial y un XLSX.
Verifica los datos de la respuesta y la auditoría de herramientas. El XLSX se
decodifica y se abre con openpyxl para comprobar que contiene stock.

El reporte `data/results/chat_validation.json` conserva resultados, códigos de
motivo y nombres de herramientas. No guarda contraseñas, tokens, respuestas
comerciales ni archivos adjuntos. El proceso termina con código 1 si un caso falla.

Puedes ejecutar casos específicos sin repetir toda la matriz:

```bash
.venv/bin/python scripts/validate_chat.py --live --case stock_screenshot_3 --case stock_xlsx
```

La regresión de capacidades puede ejecutarse por separado (7 mensajes en 6 casos).
Estos casos usan HTTP y servicios reales locales, pero se resuelven sin OpenAI:

```bash
.venv/bin/python scripts/validate_chat.py --live --case capabilities_guest_typo --case capabilities_customer --case capabilities_sales --case capabilities_admin --case capabilities_guest_history --case capabilities_customer_tools --report data/results/capabilities_validation.json
```
