# Corrección de las fronteras de métricas LLM

## Alcance

Conservar el resumen de consumo del puente al pasar a Python y preservar cada intento de retry/fallback. Sin despliegue ni proveedores externos.

## Implementación secuencial

1. Añadir regresiones con `httpx.MockTransport` que recorran LLMClient y chat: puente con subtotal 30 y cobertura 1/2; fallo 503 seguido de éxito con 30 tokens; generación simple y herramientas.
2. Ampliar `promption/metrics_aggregator.py` para combinar resúmenes sin convertir cobertura parcial en completa, conservando identificación y deduplicación de eventos.
3. Ampliar `LLMResponse` con subtotales, cobertura, desglose de llamadas y eventos por intento. Registrar las respuestas y errores de transporte de cada operación en `llm_client.py`, sin modificar fallback, seguridad o deadlines.
4. Importar los eventos en `ExecutionContext` para generación simple, herramientas y errores. Mantener compatibilidad con clientes que sólo proporcionan campos antiguos.
5. Ejecutar regresiones, suites de métricas/LLM/chat, suite Python sin live y suites Node. Verificar diff final y documentar resultados.

## Criterios de aceptación

- Puente con dos llamadas, subtotal 30 y cobertura 1/2 conserva exactamente esos datos en chat.
- Fallo sin usage más éxito de 30: dos llamadas, una fallida, total completo null, subtotal 30, cobertura 1/2.
- Eventos de scope se mantienen separados de generación.
- Cero sigue siendo cero. Eventos repetidos no duplican consumo.
- Errores y bloqueos mantienen su comportamiento de seguridad.
- Sin cambios a columnas oficiales del benchmark ni credenciales en archivos/logs.

## Verificación ejecutada

- Regresiones HTTP → cliente → chat en `tests/test_llm_metrics_boundaries.py`: puente parcial, fallback, errores finales, bloqueos, cancelación y respuesta vacía antes de fallback. Generación simple y herramientas cubiertas.
- Suite Node SDK y demo: 120 aprobadas.
- Smoke local: API health 200, dashboard sin excepciones y benchmark de 661 muestras con `use_llm=False, save=False`.
- Primera suite Python completa: 796 aprobadas y dos fallos. La aserción antigua del total tras fallback se actualizó al contrato parcial. El test CAS de Redis pasó al repetirlo; su simulador no incrementa versiones en `zadd`, por lo que su validación de WATCH es intermitente. No se modificó Redis.
- Sin llamadas a proveedores externos ni despliegue.
- Verificación final: 801 pruebas Python aprobadas, 9 live deseleccionadas, 8 advertencias de deprecación; 71 regresiones de métricas/LLM aprobadas. La prueba Redis también pasó en esta ejecución, conservando el pendiente del simulador descrito arriba.
