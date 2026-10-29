# Promption Shop: evaluación de Lúmina y datasets abiertos — 25/10/2026

## Alcance y trazabilidad

Promption **1.7.2**, perfil equilibrado. DeepSeek-V4.1-Flash-1017 mediante el alias `deepseek-flash`, razonamiento desactivado, máximo 1024 tokens por respuesta y 12 episodios concurrentes.

Estado: **completa**. 1800 de 1800 episodios, sobre 600 casos únicos. Cada condición utiliza llamadas nuevas.

600 casos: 180 conversaciones de Lúmina (90 positivos y 90 negativos) y 420 casos públicos (210 positivos y 210 negativos). Selección determinista sobre particiones de prueba previamente expuestas a diagnósticos, sin usar predicciones del filtro para elegir casos.

Corpus públicos: `{"Benigno": 210, "Jailbreak": 133, "Custom": 62, "NEPI": 12, "OWASP": 3}`. Idiomas públicos: `{"en": 398, "es": 22}`. Lúmina conserva español o mezcla de idiomas sin verificación lingüística independiente.

Las tres condiciones comparten datos, herramientas y clave sintética. Solo prompt y Promption comparten exactamente el mismo prompt protector. La condición Promption añade la librería Python, middleware AI SDK, contexto e intención, controles de permisos, MCP y protección de salida.

## Lúmina

| Condición | N | VP | FP | FN | VN | Fallos | Sin clasificar |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 180 | 63 | 0 | 8 | 85 | 1 | 23 |
| Solo prompt | 180 | 71 | 3 | 8 | 83 | 0 | 15 |
| Prompt + Promption | 180 | 86 | 5 | 3 | 78 | 7 | 1 |

| Condición | Evaluables | FPR | FNR | Recall | Precisión | F1 | Exactitud |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 156 | 0.00% | 11.27% | 88.73% | 100.00% | 94.03% | 94.87% |
| Solo prompt | 165 | 3.49% | 10.13% | 89.87% | 95.95% | 92.81% | 93.33% |
| Prompt + Promption | 172 | 6.02% | 3.37% | 96.63% | 94.51% | 95.56% | 95.35% |

| Condición | Filtraciones en cualquier caso | Objetivos predefinidos | Filtraciones en objetivos | Efectos de herramientas no autorizadas |
|---|---:|---:|---:|---:|
| Sin protección | 0 | 79 | 0 | 0 |
| Solo prompt | 0 | 79 | 0 | 0 |
| Prompt + Promption | 0 | 79 | 0 | 0 |

Origen de los FP de la condición Promption: `{"model": 1, "guard": 4}`. Los rechazos del propio modelo se conservan en la FPR del sistema completo, pero no deben atribuirse todos al guard de entrada.

## Datasets abiertos

| Condición | N | VP | FP | FN | VN | Fallos | Sin clasificar |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 420 | 161 | 38 | 48 | 162 | 9 | 2 |
| Solo prompt | 420 | 167 | 35 | 43 | 173 | 2 | 0 |
| Prompt + Promption | 420 | 188 | 45 | 19 | 162 | 6 | 0 |

| Condición | Evaluables | FPR | FNR | Recall | Precisión | F1 | Exactitud |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 409 | 19.00% | 22.97% | 77.03% | 80.90% | 78.92% | 78.97% |
| Solo prompt | 418 | 16.83% | 20.48% | 79.52% | 82.67% | 81.07% | 81.34% |
| Prompt + Promption | 414 | 21.74% | 9.18% | 90.82% | 80.69% | 85.45% | 84.54% |

| Condición | Filtraciones en cualquier caso | Objetivos predefinidos | Filtraciones en objetivos | Efectos de herramientas no autorizadas |
|---|---:|---:|---:|---:|
| Sin protección | 1 | 5 | 0 | 0 |
| Solo prompt | 0 | 5 | 0 | 0 |
| Prompt + Promption | 0 | 5 | 0 | 0 |

Origen de los FP de la condición Promption: `{"guard": 43, "model": 2}`. Los rechazos del propio modelo se conservan en la FPR del sistema completo, pero no deben atribuirse todos al guard de entrada.

## Conjunto combinado descriptivo

| Condición | N | VP | FP | FN | VN | Fallos | Sin clasificar |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 600 | 224 | 38 | 56 | 247 | 10 | 25 |
| Solo prompt | 600 | 238 | 38 | 51 | 256 | 2 | 15 |
| Prompt + Promption | 600 | 274 | 50 | 22 | 240 | 13 | 1 |

| Condición | Evaluables | FPR | FNR | Recall | Precisión | F1 | Exactitud |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sin protección | 565 | 13.33% | 20.00% | 80.00% | 85.50% | 82.66% | 83.36% |
| Solo prompt | 583 | 12.93% | 17.65% | 82.35% | 86.23% | 84.25% | 84.73% |
| Prompt + Promption | 586 | 17.24% | 7.43% | 92.57% | 84.57% | 88.39% | 87.71% |

| Condición | Filtraciones en cualquier caso | Objetivos predefinidos | Filtraciones en objetivos | Efectos de herramientas no autorizadas |
|---|---:|---:|---:|---:|
| Sin protección | 1 | 84 | 0 | 0 |
| Solo prompt | 0 | 84 | 0 | 0 |
| Prompt + Promption | 0 | 84 | 0 | 0 |

Origen de los FP de la condición Promption: `{"model": 3, "guard": 47}`. Los rechazos del propio modelo se conservan en la FPR del sistema completo, pero no deben atribuirse todos al guard de entrada.

## Definiciones y errores

FPR=FP/(FP+VN); FNR=FN/(FN+VP); recall=VP/(VP+FN); precisión=VP/(VP+FP). Se excluyen errores y casos sin clasificación del denominador, pero se conservan como columnas y no se consideran detecciones correctas.

Los VP/FP/FN/VN describen rechazo frente a etiquetas provisionales, no éxito del ataque. Las filtraciones se comprueban mediante un oráculo finito sobre la clave sintética, sus representaciones documentadas, archivos entregados y destinos web simulados. Las coincidencias en candidatos bloqueados se conservan separadas en el JSON; no equivalen a información entregada.

Los ceros observados no prueban riesgo poblacional cero. Los valores pareados de McNemar incluidos en JSON son descriptivos, porque hay dependencia por participante e historial. La muestra ampliada no permite una atribución causal simple respecto de ejecuciones anteriores con modelos o muestras distintos.

## Consumo

Llamadas de esta batería: **3154**; estados HTTP `{"200": 3154}`. Cota nueva: **US$1.490353**; acumulada: **US$4.320220**, bajo el techo de US$5.

Se usan precios pico sin descuentos por caché, no una factura. Las reservas pendientes o sin uso informado se conservan como cota superior. No hay reintentos automáticos ni pausas artificiales en DeepSeek.

## Regresión local completa de Lúmina

Se revisaron **4411 turnos**, con **13233 ejecuciones locales** en tres perfiles y cero llamadas API. El FN local significa ausencia de veto de entrada: puede continuar por revisión semántica y protección de salida, por lo que no es una medición de exfiltración.

| Perfil | N | VP | FP | FN sin veto | VN | FPR | Positivos enviados a revisión |
|---|---:|---:|---:|---:|---:|---:|---:|
| conversational | 4411 | 667 | 103 | 1566 | 2075 | 4.73% | 1566 |
| balanced | 4411 | 784 | 154 | 1449 | 2024 | 7.07% | 1449 |
| strict | 4411 | 1067 | 341 | 1166 | 1837 | 15.66% | 1166 |

## Límites

- Las etiquetas son provisionales o de origen, sin nueva adjudicación humana.
- Los rechazos se comparan con etiquetas de inyección: un FN de rechazo no equivale a un ataque exitoso y una referencia negativa no garantiza autorización de la petición.
- La mezcla pondera los corpus según su tamaño; consulta también los resultados separados de Lúmina y del corpus público.
- Hay dependencia entre conversaciones de los mismos participantes y exposición previa durante el desarrollo; no es una nueva reserva independiente.
- El generador y el juez de rechazo usan DeepSeek. Las respuestas inciertas y fallos operativos quedan separados.
- Las herramientas web e internas son fixtures con una clave sintética. No se accede a páginas externas ni a secretos reales.
- La política del experimento permite tareas generales y datos públicos de Lúmina; no reproduce todas las reglas comerciales de Shop.
- La tasa de bloqueo de actividad real no permite calcular FPR, FNR o recall sin etiquetas de referencia.

Hash del protocolo: `f091c66babfb06330a5e3049794cf4f72ebbee8cdf778fdc4107d7ad72980083`. Verificación de hashes: `True`. Las trazas privadas permanecen en `output/shop_evaluation_20261025/`; no se copian chats, credenciales ni clave real a la app.

- [Modelos y precios oficiales de DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/)

## Interpretación de los resultados finales

La condición Promption obtuvo, en el conjunto combinado, recall de rechazo 92.57%, FPR 17.24% y FNR 7.43%. En Lúmina el recall fue 96.63% con FPR 6.02%; en los corpus públicos, 90.82% con FPR 21.74%. La diferencia entre corpus no debe ocultarse mediante el agregado.

De los 22 FN de rechazo de Promption, 15 fueron aclaraciones fijas y 7 respuestas; ninguno produjo una filtración observada. De sus 50 FP contra las etiquetas de referencia, 47 se originaron en el guard y 3 en el propio modelo. Son etiquetas provisionales y requieren adjudicación antes de concluir cuántos rechazos fueron realmente indebidos.

Hubo una filtración literal completa de la clave sintética en la condición sin protección, dentro de un caso público positivo que no estaba marcado previamente como objetivo de exfiltración. Se confirmó el valor completo de forma independiente a la coincidencia por fragmentos. Por eso la tabla informa una filtración en todos los casos y cero en los 84 objetivos predefinidos. Solo prompt y Promption registraron cero filtraciones; este resultado no demuestra superioridad de Promption frente al prompt protector.

## Integración y verificación de Shop

- Tema claro, oscuro o del sistema, preferencia persistente y aplicada antes de hidratar la página. Selector en tienda, login, chat y administración; colores y gráficos adaptados a ambos temas.
- Shop consume `@promption/ai-sdk` 1.7.2 mediante dependencia local; lockfile sincronizado, transpilación del paquete y uso de `createContextEvaluator` en el middleware y en el puente de alcance. La protección sigue perteneciendo a la librería.
- Estadísticas separadas en actividad operativa y evaluación con etiquetas. Filtros por corpus, tablas de métricas, matrices de confusión, cobertura, errores y filtraciones. Los resultados agregados solo se sirven a administradores.
- El benchmark local sin LLM se identifica como proxy y no se presenta como una medición de filtraciones. Se eliminaron los ahorros predeterminados cuando no hay datos medidos.
- Build de producción y comprobación de tipos aprobadas; 1.242 pruebas Python aprobadas, 10 omitidas; 179 pruebas JavaScript aprobadas. Benchmark local de 661 registros sin llamadas LLM; dashboard Streamlit sin excepciones; API health HTTP 200.
- Verificación HTTP de sesión firmada: administrador HTTP 200 en resultados y actividad; visitante y cliente HTTP 403 en resultados. Navegador: tema claro/oscuro, persistencia tras recarga, carga de 1.800 resultados completos y selector de corpus comprobados.
- Vista previa local: http://127.0.0.1:13100/admin/estadisticas. Los cambios de esta tarea se prepararon y verificaron en el repositorio local; este informe no acredita un despliegue nuevo en producción.
