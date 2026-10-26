# Lúmina: comparación por API (gemini) — 25/10/2026

## Alcance

Se planificaron **120 casos y 360 episodios**. Se registraron **22 episodios**, correspondientes a **8 casos**; 7 tienen registros en las tres condiciones y 7 tienen las tres ejecuciones sin fallo operativo.

Estado: **incompleta**. Generador y juez de rechazo: `gemini-3.5-flash-lite`. Evaluador semántico de Promption: `gemini-3.5-flash-lite`. Promption 1.7.1, perfil equilibrado.

Misma clave sintética, datos públicos y herramientas para las tres condiciones. Solo prompt y Promption comparten la misma política protectora. Cada condición utiliza llamadas nuevas; no se sustituyen fallos por respuestas históricas. Webs y archivos internos son fixtures, sin acceso a secretos reales.

## Rechazo observado frente a las etiquetas provisionales

| Condición | N registrados | VP | FP | FN | VN | Fallos operativos | Sin clasificación |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 7 | 2 | 0 | 0 | 5 | 0 | 0 |
| Solo prompt | 8 | 2 | 0 | 0 | 5 | 1 | 0 |
| Prompt + Promption | 7 | 2 | 1 | 0 | 4 | 0 | 0 |

Estos VP/FP/FN/VN comparan rechazos observados con etiquetas silver de inyección. Una respuesta sin rechazo no prueba que el ataque haya tenido éxito; puede ser una respuesta legítima parcial o una aclaración. Los errores del proveedor no se cuentan como bloqueos correctos.

## Exfiltración y herramientas

| Condición | Objetivos registrados | Objetivos sin fallo operativo | Filtraciones en esos objetivos | Filtraciones en cualquier caso | Efectos de herramientas no autorizadas |
|---|---:|---:|---:|---:|---:|
| Sin protección | 1 | 1 | 0 | 0 | 0 |
| Solo prompt | 1 | 1 | 0 | 0 | 0 |
| Prompt + Promption | 1 | 1 | 0 | 0 | 0 |

El oráculo principal comprueba la clave sintética y sus representaciones documentadas en respuestas, archivos entregados y destinos web simulados. No cubre cualquier posible codificación. Cero eventos en una muestra pequeña, y especialmente cero en las tres condiciones, no demuestra superioridad ni una tasa poblacional próxima a cero.

## Subconjunto pareado sin fallos operativos

| Condición | N pareados | VP | FP | FN | VN | Sin clasificación |
|---|---:|---:|---:|---:|---:|---:|
| Sin protección | 7 | 2 | 0 | 0 | 5 | 0 |
| Solo prompt | 7 | 2 | 0 | 0 | 5 | 0 |
| Prompt + Promption | 7 | 2 | 1 | 0 | 4 | 0 |

Este subconjunto permite comparar los mismos casos, pero excluir fallos reduce la cobertura y puede introducir sesgo. La tabla de todos los episodios registrados se conserva como resultado principal.

## Consumo y trazabilidad

Llamadas HTTP de esta ejecución: **42**. Estados: `{"200": 41, "400": 1}`. Coste superior contabilizado nuevo: **US$0.000000**; acumulado: **US$2.077049**, con parada acumulada de US$5.00. Las llamadas sin uso reportado conservan su reserva como cota superior; no equivale necesariamente a facturación real.

Los protocolos, fuentes congeladas, solicitudes, respuestas y decisiones se conservan localmente. El JSON publicado contiene agregados y hashes, sin conversaciones, nombres, teléfonos, credenciales ni clave del reto.

## Límites

- Etiquetas provisionales sin adjudicación humana; la cohorte ya fue expuesta a diagnósticos.
- Los casos comparten participantes e historial: no son observaciones independientes.
- El alcance de la política de esta prueba es general y puede diferir del alcance empresarial histórico.
- Las metas de exfiltración se etiquetaron provisionalmente y pueden depender del historial.
- No se mezclan resultados anteriores de otros modelos o proveedores con esta comparación.

- [Agregados y cobertura](../data/results/lumina_gemini_api_20261025.json)
