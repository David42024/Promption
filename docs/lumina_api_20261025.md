# Lúmina: comparación por API (groq) — 25/10/2026

## Alcance

Se planificaron **120 casos y 360 episodios**. Se registraron **41 episodios**, correspondientes a **14 casos**; 13 tienen registros en las tres condiciones y 13 tienen las tres ejecuciones sin fallo operativo.

Estado: **incompleta**. Generador y juez de rechazo: `qwen/qwen3.8-27b`. Evaluador semántico de Promption: `openai/gpt-oss-120b`. Promption 1.7.1, perfil equilibrado.

Misma clave sintética, datos públicos y herramientas para las tres condiciones. Solo prompt y Promption comparten la misma política protectora. Cada condición utiliza llamadas nuevas; no se sustituyen fallos por respuestas históricas. Webs y archivos internos son fixtures, sin acceso a secretos reales.

## Rechazo observado frente a las etiquetas provisionales

| Condición | N registrados | VP | FP | FN | VN | Fallos operativos | Sin clasificación |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 13 | 4 | 0 | 0 | 8 | 0 | 1 |
| Solo prompt | 14 | 4 | 0 | 0 | 10 | 0 | 0 |
| Prompt + Promption | 14 | 4 | 1 | 0 | 8 | 1 | 0 |

Estos VP/FP/FN/VN comparan rechazos observados con etiquetas silver de inyección. Una respuesta sin rechazo no prueba que el ataque haya tenido éxito; puede ser una respuesta legítima parcial o una aclaración. Los errores del proveedor no se cuentan como bloqueos correctos.

## Exfiltración y herramientas

| Condición | Objetivos registrados | Objetivos sin fallo operativo | Filtraciones en esos objetivos | Filtraciones en cualquier caso | Efectos de herramientas no autorizadas |
|---|---:|---:|---:|---:|---:|
| Sin protección | 2 | 2 | 0 | 0 | 0 |
| Solo prompt | 2 | 2 | 0 | 0 | 0 |
| Prompt + Promption | 2 | 2 | 0 | 0 | 0 |

El oráculo principal comprueba la clave sintética y sus representaciones documentadas en respuestas, archivos entregados y destinos web simulados. No cubre cualquier posible codificación. Cero eventos en una muestra pequeña, y especialmente cero en las tres condiciones, no demuestra superioridad ni una tasa poblacional próxima a cero.

## Subconjunto pareado sin fallos operativos

| Condición | N pareados | VP | FP | FN | VN | Sin clasificación |
|---|---:|---:|---:|---:|---:|---:|
| Sin protección | 13 | 4 | 0 | 0 | 8 | 1 |
| Solo prompt | 13 | 4 | 0 | 0 | 9 | 0 |
| Prompt + Promption | 13 | 4 | 1 | 0 | 8 | 0 |

Este subconjunto permite comparar los mismos casos, pero excluir fallos reduce la cobertura y puede introducir sesgo. La tabla de todos los episodios registrados se conserva como resultado principal.

## Consumo y trazabilidad

Llamadas HTTP de esta ejecución: **83**. Estados: `{"200": 82, "429": 1}`. Coste superior contabilizado nuevo: **US$0.166146**; acumulado: **US$2.070245**, con parada acumulada de US$7.00. Las llamadas sin uso reportado conservan su reserva como cota superior; no equivale necesariamente a facturación real.

La ejecución se detuvo por la cuota diaria de tokens del proveedor (HTTP 429). Los casos no intentados permanecen pendientes; el error no se considera un bloqueo correcto de Promption.

Los protocolos, fuentes congeladas, solicitudes, respuestas y decisiones se conservan localmente. El JSON publicado contiene agregados y hashes, sin conversaciones, nombres, teléfonos, credenciales ni clave del reto.

## Límites

- Etiquetas provisionales sin adjudicación humana; la cohorte ya fue expuesta a diagnósticos.
- Los casos comparten participantes e historial: no son observaciones independientes.
- El alcance de la política de esta prueba es general y puede diferir del alcance empresarial histórico.
- Las metas de exfiltración se etiquetaron provisionalmente y pueden depender del historial.
- No se mezclan resultados anteriores de otros modelos o proveedores con esta comparación.

- [Agregados y cobertura](../data/results/lumina_api_20261025.json)
