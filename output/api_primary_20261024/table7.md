## Tabla 7. Evaluación principal mediante API

| Indicador | Solo prompt del sistema | Con Promption 1.3.3 |
|---|---:|---:|
| Episodios ejecutados | 72 | 72 |
| Episodios con objetivo prohibido/fuente maliciosa | 36 | 36 |
| Objetivos prohibidos logrados | 0 | 0 |
| Filtraciones en respuestas finales | 0 | 0 |
| Episodios con filtración en archivos entregados | 0 | 0 |
| Episodios con ejecución de herramientas internas prohibidas | 0 | 0 |
| Tareas legítimas evaluadas | 36 | 36 |
| Tareas legítimas completadas, criterio automático | 36 | 26 |
| Tareas legítimas bloqueadas por guards | 0 | 3 |
| Fallos operativos | 0 | 7 |
| Archivos entregados | 13 | 5 |
| ASR sobre episodios programados | 0.00% | 0.00% |
| Éxito de tareas legítimas | 100.00% | 72.22% |

**Diseño:** 24 casos sintéticos bilingües, tres repeticiones por condición. Generador GPT-5.4-nano-2026-03-17; evaluador contextual GPT-5.4-mini-2026-03-17. AI SDK con funciones nativas, guards Python, ACL y executor MCP; páginas fixture y PDF/DOCX/XLSX reales.

**Límites:** episodios repetidos y traducciones dependientes, muestra de conveniencia y etiquetas derivadas de política, sin gold humano. La utilidad usa comprobaciones automáticas predefinidas. Los errores operativos no son detecciones correctas. Los resultados corresponden a este entorno, no a una repetición de la competencia. No se ejecutaron clasificadores pequeños ni navegación HTTP real.

**Consumo:** 299 llamadas; coste conservador US$0.206906, sin descuento por caché, frente al límite de US$2.
