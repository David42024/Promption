# Correcciones posteriores a la validación de producción

## Cambios

- `chat-service/app/policy_engine.py`: permite definiciones completas y acotadas de stock; contenido añadido sigue clasificándose como antes. La referencia posterior a datos del proveedor de internet se interpreta en su contexto público, salvo menciones de empresa, stock, SKU, márgenes o datos internos.
- `config/heuristics.yaml` y `promption/resources/heuristics.yaml`: regla benigna de lectura salarial completa para rol admin. No cambia umbrales ni pesos del modelo. Las instrucciones añadidas pierden la señal benigna; las reglas maliciosas conservan prioridad. La autorización y Output Guard siguen activos.
- `promption/filter/heuristic_filter.py`: reglas benignas con restricción de roles y coincidencia completa.
- `chat-service/app/routes.py`: referencias acotadas a una solicitud anterior inexistente devuelven aclaración sin generar; resultados MCP iniciales se reutilizan por nombre y argumentos idénticos dentro de esa solicitud, conservando tier, inspección de evidencia y control de alcance; latencias de etapas sucesivas se acumulan y se mide alcance de herramientas.
- `chat-service/app/scope.py`, `demo/app/api/ai/scope/route.js`, `demo/app/api/ai/turn/route.js`: fallos de alcance se correlacionan por request_id, con motivo y estado sanitizados. No se registran cuerpos, prompts ni credenciales.
- `tests/test_scope_hardening.py`: regresiones de definiciones y datos añadidos, conectividad y proveedores internos, lectura salarial por rol y ataques añadidos, referencia con/sin historial, acumulación de tiempos y reutilización MCP con argumentos iguales/distintos.

## Límites de lo verificado

El fallo aislado scope_unavailable de producción no tiene causa demostrada con las respuestas públicas. Se mejoró la observabilidad y se mantiene el bloqueo seguro; no se añadió reintento ciego ni se afirma que desapareció el fallo del proveedor.

La etapa scope acumula las evaluaciones realizadas por el Chat Service. Las evaluaciones internas del bridge siguen incluidas en el tiempo de su generación remota; no se debe interpretar el tiempo de scope local como desglose completo de todas las llamadas remotas.

La desconexión de Ollama corresponde a la capacidad de benchmark de la Filter API; no impide el chat configurado con OpenAI. No se cambiaron proveedores, modelos, secretos o configuración de despliegue.

Estas correcciones son locales. La reducción de falsos positivos y latencias reales debe medirse al desplegarlas y repetir el benchmark pequeño de producción. Las pruebas locales usan casos controlados, sin llamadas pagadas al LLM.

## Verificación

Logs de Python: scope-fixes-tests-final.txt; Node: scope-fixes-node.txt; compilación Next.js: scope-fixes-build.txt. Smoke de API y benchmark: scope-fixes-smoke.txt. Dashboard: scope-fixes-dashboard.txt.

Benchmark proxy ejecutado sobre 661 casos con save=False, sin sobrescribir los artefactos oficiales. API health y dashboard health respondieron HTTP 200. La compilación Next.js completó correctamente.

Resultado final: 867 pruebas Python aprobadas, 9 live_llm excluidas y 8 avisos de deprecación. Node: 136 aprobadas, sin fallos. Build Next.js correcto.
