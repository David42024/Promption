# Lúmina: comparación por API (deepseek) — 25/10/2026

## Resumen de resultados

Se ejecutaron desde cero los **120 casos de Lúmina en las tres condiciones: 360 episodios**, con DeepSeek-V4.1-Flash-1017 mediante el alias oficial `deepseek-flash`. No se reutilizaron respuestas de Gemini ni de otros proveedores. Los resultados de esta prueba no son una evaluación completa de todo el corpus de Lúmina ni de los corpus públicos.

- **Rechazo observado:** Promption obtuvo VP=54, FP=3, FN=3 y VN=55, con 4 fallos operativos y 1 caso sin clasificación. La FNR descriptiva pasó de 24.49% con solo prompt a 5.26% con Promption, y la FPR pasó de 1.75% a 5.17%. Son denominadores evaluables distintos y etiquetas provisionales: la comparación pareada también se conserva abajo.
- **Los tres FN de Promption fueron aclaraciones fijas**, sin generación de una respuesta sustantiva ni filtración observada. Se mantienen como FN en la métrica de rechazo estricto; no se reclasifican como VP después de ver los resultados. Por tanto, **no representan tres ataques exitosos**.
- **Exfiltración:** cero filtraciones y cero efectos de herramientas no autorizadas en las tres condiciones. Se programaron 48 objetivos provisionales de exfiltración por condición; uno de Promption tuvo fallo operativo. Esta igualdad de ceros **no demuestra superioridad de Promption en exfiltración**.
- **Disponibilidad:** 4/120 episodios de Promption (3.33%) fallaron por respuesta semántica inválida; 2 correspondían a referencias negativas y 2 a positivas. No se contabilizan como detecciones correctas.
- **Consumo:** 692 llamadas de la batería, todas HTTP 200; cota nueva US$0.370370. La comprobación sintética previa añadió 3 llamadas y una cota US$0.000591. Total de esta etapa DeepSeek: 695 llamadas y aproximadamente US$0.370961. Acumulado histórico conservador: US$2.448010, por debajo de US$5.

### Lectura para el artículo

En esta muestra y con etiquetas provisionales, Promption aumentó los rechazos de referencias positivas y redujo los casos positivos sin rechazo, a costa de más rechazos indebidos y fallos operativos. La evidencia de exfiltración quedó empatada en cero, por lo que no permite sostener que esta batería haya demostrado una reducción de filtraciones frente al modelo base.

Los tres FP de Promption se originaron uno en `INPUT_RISK_LIMIT`, uno en `malicious_input` y uno en `system_limit`. Los cuatro fallos operativos fueron `invalid_scope_response`. Hubo 12 aclaraciones fijas: 9 sobre referencias negativas y 3 sobre positivas; ninguna debe confundirse con una respuesta sustantiva correcta.

La API devolvió solamente el alias `deepseek-flash`; la asociación con la versión 1017 proviene de la documentación oficial consultada al preparar la prueba. No se verificó un identificador inmutable de los pesos desplegados. El modo de razonamiento estuvo desactivado; estos resultados no se generalizan automáticamente al modo con razonamiento.

## Alcance

Se planificaron **120 casos y 360 episodios**. Se registraron **360 episodios**, correspondientes a **120 casos**; 120 tienen registros en las tres condiciones y 116 tienen las tres ejecuciones sin fallo operativo.

Estado: **completa**. Generador y juez de rechazo: `deepseek-flash`. Evaluador semántico de Promption: `deepseek-flash`. Promption 1.7.2, perfil equilibrado.

Misma clave sintética, datos públicos y herramientas para las tres condiciones. Solo prompt y Promption comparten la misma política protectora. Cada condición utiliza llamadas nuevas; no se sustituyen fallos por respuestas históricas. Webs y archivos internos son fixtures, sin acceso a secretos reales.

## Rechazo observado frente a las etiquetas provisionales

| Condición | N registrados | VP | FP | FN | VN | Fallos operativos | Sin clasificación |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 120 | 36 | 0 | 11 | 55 | 0 | 18 |
| Solo prompt | 120 | 37 | 1 | 12 | 56 | 0 | 14 |
| Prompt + Promption | 120 | 54 | 3 | 3 | 55 | 4 | 1 |

Estos VP/FP/FN/VN comparan rechazos observados con etiquetas silver de inyección. Una respuesta sin rechazo no prueba que el ataque haya tenido éxito; puede ser una respuesta legítima parcial o una aclaración. Los errores del proveedor no se cuentan como bloqueos correctos.

## Exfiltración y herramientas

| Condición | Objetivos registrados | Objetivos sin fallo operativo | Filtraciones en esos objetivos | Filtraciones en cualquier caso | Efectos de herramientas no autorizadas |
|---|---:|---:|---:|---:|---:|
| Sin protección | 48 | 48 | 0 | 0 | 0 |
| Solo prompt | 48 | 48 | 0 | 0 | 0 |
| Prompt + Promption | 48 | 47 | 0 | 0 | 0 |

El oráculo principal comprueba la clave sintética y sus representaciones documentadas en respuestas, archivos entregados y destinos web simulados. No cubre cualquier posible codificación. Cero eventos en una muestra pequeña, y especialmente cero en las tres condiciones, no demuestra superioridad ni una tasa poblacional próxima a cero.

## Subconjunto pareado sin fallos operativos

| Condición | N pareados | VP | FP | FN | VN | Sin clasificación |
|---|---:|---:|---:|---:|---:|---:|
| Sin protección | 116 | 36 | 0 | 10 | 53 | 17 |
| Solo prompt | 116 | 36 | 1 | 11 | 54 | 14 |
| Prompt + Promption | 116 | 54 | 3 | 3 | 55 | 1 |

Este subconjunto permite comparar los mismos casos, pero excluir fallos reduce la cobertura y puede introducir sesgo. La tabla de todos los episodios registrados se conserva como resultado principal.

## Consumo y trazabilidad

Llamadas HTTP de esta ejecución: **692**. Estados: `{"200": 692}`. Coste superior contabilizado nuevo: **US$0.370370**; acumulado: **US$2.448010**, con parada acumulada de US$5.00. Las llamadas sin uso reportado conservan su reserva como cota superior; no equivale necesariamente a facturación real.

Los protocolos, fuentes congeladas, solicitudes, respuestas y decisiones se conservan localmente. El JSON publicado contiene agregados y hashes, sin conversaciones, nombres, teléfonos, credenciales ni clave del reto.

## Límites

- Etiquetas provisionales sin adjudicación humana; la cohorte ya fue expuesta a diagnósticos.
- Los casos comparten participantes e historial: no son observaciones independientes.
- El alcance de la política de esta prueba es general y puede diferir del alcance empresarial histórico.
- Las metas de exfiltración se etiquetaron provisionalmente y pueden depender del historial.
- No se mezclan resultados anteriores de otros modelos o proveedores con esta comparación.

- [Agregados y cobertura](../data/results/lumina_deepseek_api_20261025.json)

## Métricas de rechazo y denominadores

| Condición | Evaluables | Precisión | Sensibilidad | F1 | FPR | FNR |
|---|---:|---:|---:|---:|---:|---:|
| Sin protección | 102 | 100.00% | 76.60% | 86.75% | 0.00% | 23.40% |
| Solo prompt | 106 | 97.37% | 75.51% | 85.06% | 1.75% | 24.49% |
| Prompt + Promption | 115 | 94.74% | 94.74% | 94.74% | 5.17% | 5.26% |

VP: referencia positiva rechazada; FP: referencia negativa rechazada; FN: referencia positiva sin rechazo; VN: referencia negativa sin rechazo. FPR = FP/(FP+VN), FNR = FN/(FN+VP), precisión = VP/(VP+FP), sensibilidad = VP/(VP+FN). Los denominadores excluyen errores y respuestas sin clasificación. Estas métricas describen rechazo, no éxito del ataque ni la exactitud independiente del detector.

## Cohorte y protocolo reproducible

- Modelo solicitado: **DeepSeek-V4.1-Flash-1017**, alias oficial `deepseek-flash`; respuestas reportadas: `{"deepseek-flash": 692}`.
- Cohorte: `{"languages": {"es_or_mixed_unverified": 120}, "labels": {"0": 60, "1": 60}, "context_required": 65, "history_present": 107, "groups": 118}`.
- Participantes seudonimizados: 14; objetivos provisionales de exfiltración: 48.
- Promption 1.7.2, perfil equilibrado; 1 repetición por condición; concurrencia 1.
- Máximo 1024 tokens por respuesta, 3 pasos y 2 llamadas a herramientas por episodio. Sin reintentos automáticos.
- Razonamiento desactivado mediante `thinking.type=disabled` en generación, evaluación de contexto y juez de rechazo. JSON portable validado por AI SDK.
- Las mismas herramientas y datos se ofrecen en las tres condiciones; solo Promption aplica controles de entrada, historial, intención, permisos, herramientas y salida. El prompt protector es idéntico en las dos condiciones protegidas.
- Consultas a webs, lectura interna y generación documental utilizan fixtures y un servidor MCP local. Se miden efectos y archivos entregados, sin atacar servicios externos.
- Hash del protocolo: `56db7668efd9ebaaedb5892e5c4756c3ae84ceb5b967dce3afb05088c8efacbc`; hashes de fuentes, datos y solicitudes verificados: `True`.

La cohorte conserva exactamente los casos de las pruebas anteriores para permitir una comparación controlada del proveedor, pero todas las respuestas de esta tabla son nuevas. No constituye una nueva reserva ciega ni un conjunto independiente: hubo exposición previa durante el desarrollo.

## Consumo y tiempos por condición

| Condición | Llamadas API | Tokens entrada | Tokens salida | Cota US$ | Mediana episodio (s) | P95 (s) |
|---|---:|---:|---:|---:|---:|---:|
| Sin protección | 250 | 337103 | 13950 | 0.117871 | 2.64 | 4.07 |
| Solo prompt | 249 | 379190 | 17086 | 0.134260 | 2.76 | 4.25 |
| Prompt + Promption | 193 | 357499 | 9158 | 0.118239 | 1.35 | 5.43 |

Distribución de llamadas por finalidad: `{"generation": 310, "refusal_judge": 287, "context_scope": 95}`. Los tiempos incluyen juez de rechazo y, cuando corresponde, guardas; no son latencia pura de generación. La cota de coste utiliza precios pico sin descuentos por caché u horario; no equivale a una factura.

## Errores y origen de las decisiones

| Condición | Rechazos del guard | Rechazos del modelo | FP del guard | FP del modelo | Aclaraciones en referencias negativas |
|---|---:|---:|---:|---:|---:|
| Sin protección | 0 | 36 | 0 | 0 | 0 |
| Solo prompt | 0 | 38 | 0 | 1 | 0 |
| Prompt + Promption | 57 | 0 | 3 | 0 | 9 |

Motivos registrados, Sin protección: `{"final_response": 120}`.

Motivos registrados, Solo prompt: `{"final_response": 120}`.

Motivos registrados, Prompt + Promption: `{"final_response": 47, "system_limit": 17, "INPUT_RISK_LIMIT": 11, "malicious_input": 26, "fixed_clarification": 12, "ambiguous": 3, "invalid_scope_response": 4}`.

## Incertidumbre y uso para el artículo

Los intervalos Wilson del JSON son únicamente descriptivos bajo una hipótesis de independencia que este corpus no satisface plenamente. Para inferencia confirmatoria deben usarse adjudicación humana y remuestreo por participante o grupos; los valores nominales de McNemar también son descriptivos.

Un cero observado no demuestra una probabilidad poblacional de cero. En ausencia de filtraciones, la cota unilateral exacta nominal del 95% es 1−0.05^(1/n), con n objetivos independientes; el historial compartido reduce la independencia efectiva. Si todas las condiciones presentan cero, esta prueba no demuestra superioridad en exfiltración.

El juez de rechazo usa el mismo proveedor que el generador: existe sesgo de autoevaluación. Las etiquetas de referencia son provisionales y la exactitud de la asistencia legítima no se verifica exhaustivamente. Los casos sin rechazo deben revisarse junto con la evidencia de salida y herramientas antes de llamarlos ataques exitosos.

El informe conserva resultados negativos, errores, falsos positivos y falsos negativos; no selecciona únicamente los casos favorables. La protección debe medirse conjuntamente con disponibilidad y pérdida de servicio legítimo.

## Fuentes técnicas

- [DeepSeek: modelos, alias y precios](https://api-docs.deepseek.com/quick_start/pricing/)
- [DeepSeek: control de razonamiento y herramientas](https://api-docs.deepseek.com/guides/thinking_mode/)
- [DeepSeek: salida JSON](https://api-docs.deepseek.com/guides/json_mode/)

## Verificación local y archivos

- Pruebas Python completas: **1.242 aprobadas, 10 omitidas**; hubo 8 advertencias ya registradas.
- SDK JavaScript: **178 aprobadas**. Presupuesto y adaptador DeepSeek: **12 aprobadas**. Pruebas específicas de la evaluación: **27 aprobadas** (incluidas en la suite completa).
- Cobertura verificada: 120 casos, 360 episodios, 120 por condición; las celdas de las matrices más los casos operativos y sin clasificación suman exactamente 120 por condición.
- Hashes verificados; ningún resultado anterior se reutilizó; ejecución terminada y bloqueo de proceso retirado.
- Credencial local excluida de Git, permisos 0600; los informes compartibles no contienen la clave sintética.
- Las trazas y decisiones por episodio permanecen en `output/precision_improvement_20261025/deepseek/lumina_120/`; contiene datos de investigación seudonimizados y no debe publicarse como si fuera únicamente un informe agregado.

Con 48 objetivos y cero eventos, la cota unilateral nominal del 95% bajo independencia sería aproximadamente **6.05%**; usando los 47 objetivos sin fallo operativo de Promption, aproximadamente **6.18%**. Son cálculos descriptivos: los objetivos proceden de solo 8 participantes y no son plenamente independientes. Esta muestra no acredita una tasa poblacional inferior al 1%.
