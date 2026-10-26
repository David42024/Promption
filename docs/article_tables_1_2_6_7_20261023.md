# Tablas 1, 2, 6 y 7 para el artículo de Promption

Actualizadas el 25/10/2026. La tabla 7 conserva la primera evaluación 1.3.3
y añade la repetición completa 1.4.0: los mismos 240 casos, 720 episodios nuevos
en tres condiciones, sin sumarlos como casos independientes. Las tablas 7C–7E
presentan la repetición y la comparación con rúbrica común. El gasto acumulado
con la prueba sintética anterior era US$1.503472. La comparación posterior de
perfiles (tabla 7F) deja el acumulado en US$1.669110 de US$2. La numeración sigue la
propuesta del artículo; cada resultado identifica su versión.

## Tabla 1. Componentes e integración de la librería Promption

| Componente | Función | Integración disponible | Alcance y condiciones |
|---|---|---|---|
| Filtro heurístico | Detectar patrones de inyección mediante reglas y normalización | `promption.filter`, Filter API | Reglas YAML; coincidencias benignas completas y vetos maliciosos |
| Clasificación y ensemble | Combinar detectores y decidir bloqueo o revisión adicional | `EnsembleFilter`, API | OR entre capas ejecutadas; backend ligero TF-IDF + regresión logística disponible; el artefacto entrenado se suministra aparte |
| Guard conversacional | Analizar instrucciones fragmentadas, referencias, alias e historial | `ConversationGuard`, middleware AI SDK | Conserva procedencia; 1.4.0 coordina aislamiento validado de historial con el middleware y exige Output Guard |
| Alcance e intención | Evaluar la petición según política, intención, historial y herramienta propuesta | `ContextScopeGuard`, `AsyncContextScopeGuard`, `createContextEvaluator` | Evaluador configurable; una aprobación semántica no elimina otros vetos |
| Autorización de recursos y herramientas | Comprobar identidad, roles, recursos y operaciones | `PolicyEngine`, `MCPToolExecutor`, `protectTool` | Políticas e identidad proporcionadas por el servidor de la aplicación |
| Guard de salida | Detectar o redactar contenido protegido antes de entregarlo | `promption.output_guard`, `check_output`, middleware | Requiere configurar información protegida y revisar también contenido de archivos |
| Integración y observabilidad | Componer controles, comunicar decisiones y facilitar auditoría | Paquetes Python y `@promption/ai-sdk`, API y registros estructurados | Versión local 1.4.0; Python >=3.10; middleware compatible con AI SDK 6 |
| Adaptador de clasificadores pequeños | Incorporar un clasificador Transformer como capa adicional | `SmallModelFilter`; extra opcional `small-models` | Implementado y probado con dobles de prueba; pesos BERT/DeBERTa no instalados ni evaluados en estos resultados |

**Nota.** La implementación de una capacidad no implica que su eficacia haya sido
medida en el estudio. Los modelos entrenados no se incluyen automáticamente en el
wheel. Las políticas de negocio pertenecen a la aplicación consumidora.

## Tabla 2. Población, unidades de análisis y subconjuntos utilizados

| Fuente o subconjunto | Unidad | Cantidad | Criterio e interpretación |
|---|---|---:|---|
| Exportación de la competencia | Participantes | 125 | Incluye una cuenta técnica descalificada |
| Exportación de la competencia | Conversaciones con turnos | 783 | No incluye conversaciones vacías |
| Exportación de la competencia | Turnos registrados | 5262 | Universo de registros de ejecución de la exportación |
| Piloto anterior al reinicio | Turnos | 31 | Se conserva separado de la cohorte principal |
| Cohorte posterior al reinicio | Turnos | 5231 | Cohorte observacional principal |
| Exclusiones operativas posteriores al reinicio | Turnos | 208 | Estado técnico, límite de conversación o desvío a controles de spam/flood |
| Cohorte potencialmente evaluable | Turnos | 5023 | 5231 menos 208; cada matriz excluye además etiquetas o decisiones desconocidas |
| Ranking reconstruido | Prompts contabilizados | 5038 | Contador de participación; no equivale a ataques ni a casos de evaluación |
| Pozo reconstruido | Aportes completos equivalentes | 4954 | 495400 unidades de contribución divididas entre 100; no es el total de turnos |
| Auditoría de la exportación | Eventos | 88559 | Un turno puede producir varios eventos; no son observaciones independientes |
| Comparación de detectores: competencia | Mensajes individuales | 179 | 130 positivos y 49 negativos de referencia provisional; sin reconstrucción conversacional en esta comparación |
| Comparación de detectores: corpus anterior | Mensajes individuales | 661 | 302 positivos y 359 negativos según las etiquetas del benchmark; corpus distinto de la competencia |
| Corrección del historial: cohorte ampliada | Casos conversacionales | 420 | 328 positivos y 92 negativos provisionales; reproducción local de 1.3.2 frente a 1.3.3 |
| Corrección del historial: submuestra anterior | Casos conversacionales | 40 | Subconjunto de los 420; no debe sumarse como muestra independiente |
| Comparación semántica válida con proveedor | Casos reales pareados | 37 | De 40 seleccionados; 19 positivos y 18 negativos de política con dictámenes comparables |
| Prueba API sintética anterior, 24/10/2026 | Casos sintéticos distintos | 24 | 12 tareas legítimas y 12 episodios con objetivo prohibido o fuente maliciosa; 12 casos en cada idioma |
| Prueba API sintética anterior, ambas condiciones | Ejecuciones de episodios | 144 | 24 casos × 3 repeticiones × 2 condiciones; se conserva separada |
| Evaluación local actual de referencia | Mensajes individuales | 7823 | Corpus completo; incluye exposición de entrenamiento/desarrollo, no un test independiente |
| Evaluación local actual de Lúmina | Turnos con etiqueta de inyección conocida | 4411 | Vista individual y acumulada; referencia silver |
| Evaluación principal API actual | Casos distintos | 240 | 120 Lúmina y 120 referencia; 60 positivos y 60 negativos por corpus; selección reservada por manifiesto |
| Evaluación principal API actual | Ejecuciones de episodios | 720 | 240 casos × tres condiciones, una ejecución por caso/condición |
| Objetivos de exfiltración de la muestra API | Casos distintos | 49 | 48 Lúmina y uno de referencia, identificados provisionalmente antes de ejecutar |

**Notas.** Las filas describen universos, contadores y subconjuntos diferentes: no
deben sumarse. La exportación no tiene etiquetas adjudicadas por humanos. Las
anotaciones de la competencia son provisionales, con casos indeterminados y
desacuerdos. La composición lingüística de cada subconjunto no se cuantificó aquí;
no se asigna todo el tráfico a español ni se atribuyen resultados por idioma sin
un desglose verificable. Las 5023 ejecuciones potencialmente evaluables dieron
4411 casos en la matriz provisional de inyección de entrada y 4394 en la de
denegación de solicitudes según política, por sus exclusiones específicas.
La muestra API actual de referencia contiene 98 registros marcados inglés y 22
español por la fuente, con ejemplos mixtos. La de Lúmina no tiene idioma adjudicado.
La selección reservada ya había aparecido en diagnósticos previos: no es un nuevo
test ciego; las dependencias entre participantes y familias deben conservarse.

## Tabla 6. Comparación exploratoria de configuraciones de detección de entrada

| Corpus | Configuración | N | TP | FP | FN | TN | Recall (%) | FPR (%) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Competencia | Perfil base 1.1.1 | 179 | 46 | 2 | 84 | 47 | 35.38 | 4.08 |
| Competencia | Solo recalibración de umbral | 179 | 49 | 3 | 81 | 46 | 37.69 | 6.12 |
| Competencia | Reemplazo por detector adaptado con ventanas | 179 | 93 | 1 | 37 | 48 | 71.54 | 2.04 |
| Competencia | Base OR detector complementario | 179 | 88 | 2 | 42 | 47 | 67.69 | 4.08 |
| Corpus anterior | Perfil base 1.1.1 | 661 | 245 | 48 | 57 | 311 | 81.13 | 13.37 |
| Corpus anterior | Solo recalibración de umbral | 661 | 245 | 48 | 57 | 311 | 81.13 | 13.37 |
| Corpus anterior | Reemplazo por detector adaptado con ventanas | 661 | 232 | 48 | 70 | 311 | 76.82 | 13.37 |
| Corpus anterior | Base OR detector complementario | 661 | 247 | 48 | 55 | 311 | 81.79 | 13.37 |

**Definiciones.** Positivo: texto etiquetado como malicioso en el corpus respectivo.
TP: positivo bloqueado; FP: negativo bloqueado; FN: positivo no bloqueado; TN:
negativo no bloqueado. Recall = TP/(TP+FN); FPR = FP/(FP+TN). Los dos corpus no
deben asumirse equivalentes en política, dificultad o prevalencia.

**Interpretación.** Esta es una comparación de estrategias, no una ablación completa
de todas las capas. Se ejecutó localmente, sin LLM, en el experimento de la versión
1.2.0. El reemplazo mejora la competencia pero empeora el corpus anterior. La
composición OR usa umbral base 0.66 y complementario 0.82; el reemplazo adaptado usa
0.71, ventanas de 500 caracteres y solapamiento de 100. El perfil complementario es
optativo y no sustituye el perfil predeterminado.

Las etiquetas de la competencia son silver. Los casos de prueba ya habían aparecido
en diagnósticos de reglas; la composición OR fue un seguimiento exploratorio tras
observar el reemplazo. No constituye una nueva prueba ciega ni permite atribuir
causalmente mejoras a cada mecanismo por separado. No se midieron aquí generación,
eficacia del guard de salida, ASR, herramientas, latencia comparativa ni intervalos
de confianza. Las celdas de una ablación completa aún requieren nuevos experimentos.

### Tabla 6B. Detección local actual, subconjuntos reservados existentes

| Corpus / vista, Promption 1.3.3 | N | TP | FP | FN | TN | No evaluables |
|---|---:|---:|---:|---:|---:|---:|
| Referencia, mensaje individual | 661 | 245 | 48 | 57 | 311 | 0 |
| Lúmina por participante test, mensaje individual | 821 | 110 | 13 | 279 | 419 | 0 |
| Lúmina por participante test, historial acumulado | 821 | 292 | 39 | 95 | 393 | 2 |

Estos subconjuntos no se suman a la tabla 6 ni a sus corpus completos. No miden
generación ni exfiltración, y tampoco constituyen una ablación de todas las capas.
La vista acumulada detecta más positivos y también bloquea más negativos.

## Tabla 7. Evaluación principal API: tres condiciones sobre Lúmina y referencia

### 7A. Rechazo observado frente a las etiquetas de origen

| Corpus | Condición | TP | FP | FN | TN | FPR evaluable | Fallos operativos | Indeterminados |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Lúmina | Sin protección de aplicación | 40 | 1 | 16 | 53 | 1.85% | 1 | 9 |
| Lúmina | Solo prompt | 42 | 1 | 17 | 53 | 1.85% | 0 | 7 |
| Lúmina | Prompt + Promption | 59 | 16 | 0 | 38 | 29.63% | 5 | 2 |
| Referencia | Sin protección de aplicación | 41 | 15 | 16 | 38 | 28.30% | 5 | 5 |
| Referencia | Solo prompt | 45 | 8 | 14 | 48 | 14.29% | 1 | 4 |
| Referencia | Prompt + Promption | 56 | 22 | 3 | 26 | 45.83% | 10 | 3 |
| Combinado equilibrado | Sin protección de aplicación | 81 | 16 | 32 | 91 | 14.95% | 6 | 14 |
| Combinado equilibrado | Solo prompt | 87 | 9 | 31 | 101 | 8.18% | 1 | 11 |
| Combinado equilibrado | Prompt + Promption | 115 | 38 | 3 | 64 | 37.25% | 15 | 5 |

**Definiciones:** positivo es etiqueta positiva de la fuente; predicción positiva
es rechazo observado, mediante bloqueo del guard o juez de respuesta. Un FN es
una solicitud no rechazada, **no una filtración confirmada**. Las etiquetas son
silver/de origen y el juez es automático. Se detectó al menos una corrección
factual clasificada como rechazo en las tres condiciones; las cifras originales
se conservan pendientes de adjudicación humana. Los fallos e indeterminados no
entran en los denominadores evaluables. La ausencia afecta desigualmente a las
clases: en Promption faltan dos positivos y dieciocho negativos de 120 por clase.

### 7B. Exfiltración instrumentada y efectos de herramientas

| Indicador | Sin protección de aplicación | Solo prompt | Prompt + Promption |
|---|---:|---:|---:|
| Casos ejecutados por condición | 240 | 240 | 240 |
| Casos dirigidos a exfiltrar, anotación provisional | 49 | 49 | 49 |
| Exfiltraciones detectadas en esos casos | 0/49 | 0/49 | 0/49 |
| Exfiltraciones detectadas en cualquier caso | 0 | 0 | 0 |
| Fallos operativos entre los 49 casos dirigidos | 0 | 0 | 0 |
| Episodios con herramienta interna no autorizada ejecutada | 1 | 0 | 0 |
| Archivos efectivamente entregados | 5 | 5 | 0 |

**Diseño:** generador GPT-5.4-nano-2026-03-17; guard contextual
GPT-5.4-mini-2026-03-17. AI SDK y MCP oficiales; políticas, ACL y guard de salida.
Sin protección significa sin seguridad añadida por la aplicación: permanecen las
protecciones intrínsecas del proveedor. Historial fijo de Lúmina en las tres
condiciones; páginas fixture, no navegación HTTP real; archivos generados de
verdad. Perfil predeterminado 1.3.3, sin ajuste durante la evaluación ni modelos
BERT/DeBERTa. El corpus de referencia combina datos públicos y ejemplos locales.

**Oráculo:** clave sintética, transformaciones conocidas, fragmentos literales de
al menos ocho caracteres, texto final, archivos entregados y destinos web
simulados. No descarta codificaciones arbitrarias o canales no instrumentados.
El único objetivo público de exfiltración no representa sus 60 jailbreaks. Cero en
49 casos, aun suponiendo independencia, deja un límite superior unilateral del
95% de 5.93%; las dependencias reales añaden limitaciones.

**Resultado:** mayor rechazo de positivos de referencia, con más falsos rechazos.
No se ha demostrado reducción diferencial de exfiltración: todas las condiciones
dieron cero. Los archivos entregados no tienen aquí una rúbrica de éxito de tarea.
La autorización fue violada una vez sin protección, sin clave entregada al usuario.

**Consumo nuevo:** 1329 solicitudes, US$0.6215765; gasto compartido con la prueba
anterior, US$0.82848265 de US$2. Informe y rúbrica de revisión:
[evaluación de tres condiciones](corpus_three_conditions_20261024.md).

### 7C. Repetición 1.4.0: cohorte combinada equilibrada

| Condición | TP | FP | FN | TN | FPR evaluable | FNR evaluable | Fallos operativos | Indeterminados |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Sin protección de aplicación | 71 | 4 | 40 | 100 | 3.85% | 36.04% | 5 | 20 |
| Solo prompt | 69 | 5 | 48 | 105 | 4.55% | 41.03% | 2 | 11 |
| Prompt + Promption 1.4.0 | 112 | 32 | 5 | 77 | 29.36% | 4.27% | 9 | 5 |

### 7D. Versiones protegidas con la misma rúbrica de rechazo

| Corpus | Versión | TP | FP | FN | TN | FPR evaluable | Fallos operativos | Indeterminados |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| lumina | 1.3.3_rejudged | 59 | 15 | 0 | 38 | 28.30% | 5 | 3 |
| lumina | 1.4.0 | 55 | 10 | 2 | 45 | 18.18% | 4 | 4 |
| public | 1.3.3_rejudged | 56 | 20 | 4 | 30 | 40.00% | 10 | 0 |
| public | 1.4.0 | 57 | 22 | 3 | 32 | 40.74% | 5 | 1 |
| pooled_balanced_design | 1.3.3_rejudged | 115 | 35 | 4 | 68 | 33.98% | 15 | 3 |
| pooled_balanced_design | 1.4.0 | 112 | 32 | 5 | 77 | 29.36% | 9 | 5 |

La mejora agregada es **moderada**: FP 35→32, FPR 33.98%→29.36% (−4.62 puntos
porcentuales), con denominadores evaluables distintos (103→109 negativos). En
Lúmina baja 28.30%→18.18%; en referencia sube ligeramente 40.00%→40.74%. Los FN
de rechazo pasan 4→5 y el recall 96.64%→95.73%. No hay una mejora uniforme ni
una reducción demostrada de todos los errores.

En los 100 negativos con dictamen comparable en ambas versiones, diez rechazos
se convierten en no rechazos y tres casos antes no rechazados se rechazan. Los
otros 20 negativos no entran en ese pareado por falta de dictamen en una versión.
Entre los positivos comparables, dos pasan de rechazo a no rechazo y uno en sentido
inverso. No se calculó significación estadística ignorando la dependencia de participantes.

En 1.4.0 hubo **3 aclaraciones fijas**, todas en negativos de referencia; cuentan
como no rechazo, pero no prueban completar la tarea. Hubo cinco aislamientos de
historial, verificados en las cinco peticiones reales al generador: solo política
del sistema y mensaje actual; uno de esos episodios fue bloqueado después por otro
control. Los fallos operativos protegidos bajan 15→9, mientras los indeterminados
suben 3→5. Entre negativos protegidos hubo 79 respuestas, 31 bloqueos, tres
aclaraciones y siete fallos; una respuesta generada se clasificó como rechazo.

### 7E. Exfiltración y herramientas, repetición 1.4.0

| Indicador | Sin protección de aplicación | Solo prompt | Prompt + Promption |
|---|---:|---:|---:|
| Objetivos de exfiltración | 49 | 49 | 49 |
| Exfiltraciones detectadas en objetivos | 0 | 0 | 0 |
| Fallos operativos entre objetivos | 0 | 0 | 1 |
| Episodios con herramienta no autorizada ejecutada | 1 | 0 | 0 |
| Archivos entregados | 6 | 2 | 0 |

No se detectó clave entregada en ninguna condición: **0/49 objetivos**, tampoco
en los otros casos ni en los candidatos registrados. Promption tuvo un fallo
operativo entre esos 49, por lo que la tasa sobre sus casos no operativos es 0/48.
La revisión dirigida de quince respuestas sobre fragmentos cortos, estadísticas
y acrósticos encontró únicamente rechazos o bloqueos. Es una inspección posterior
del analista IA, no una validación humana exhaustiva.

La herramienta interna no autorizada se ejecutó una vez sin protección añadida
y ninguna con solo prompt o Promption. No se entregó la clave. El resultado de
exfiltración **no permite atribuir ventaja diferencial a Promption**: las tres
condiciones dieron cero. Con 49 casos independientes, cero eventos todavía deja
un límite superior unilateral nominal del 95% de 5.93%; hay además dependencias reales.


**Consumo adicional:** 1354 intentos de llamada para los 720 episodios y 75 para
reclasificar respuestas antiguas; 1427 HTTP 200 y dos tiempos de espera sin
reintentos, contabilizados con reserva íntegra. US$0.674990 nuevos; acumulado
US$1.503472. [Informe de repetición 1.4.0](corpus_repeat_140_20261024.md).

### 7F. Comparación posterior de perfiles de Promption 1.5.0

Misma submuestra de 48 casos en tres perfiles: **144 episodios nuevos**, 24 Lúmina
y 24 referencia, doce positivos y doce negativos por corpus. La selección usa
SHA-256 de semilla e ID y estratos de idioma/necesidad anotada de contexto, sin
predicciones. Es un subconjunto de los 240 casos ya expuestos, no casos nuevos
independientes. No se suman estas ejecuciones a los 720 como tamaño muestral.

| Perfil | TP | FP | FN | TN | FPR evaluable | Fallos operativos | Indeterminados | Aclaraciones fijas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| conversational | 22 | 3 | 2 | 16 | 15.79% (3/19) | 4 | 1 | 1 |
| balanced | 20 | 5 | 3 | 16 | 23.81% (5/21) | 3 | 1 | 1 |
| strict | 24 | 24 | 0 | 0 | 100.00% (24/24) | 0 | 0 | 0 |

**Interpretación:** matriz de rechazo frente a etiquetas de inyección de origen,
no de éxito del ataque. Las aclaraciones no son tareas completadas. Los negativos
sin dictamen son cinco y tres en los primeros dos perfiles; falta además un positivo
en balanced. El estricto bloqueó todo y no es útil para atención general en esta
muestra. Sobre los 72 dictámenes semánticos guardados no se activó ninguna
diferencia propia de aclaración entre conversational y balanced: los resultados
no demuestran una ventaja causal de un perfil, con llamadas independientes del
modelo y una etiqueta negativa discutible entre los dos rechazos adicionales.

Los tres perfiles tuvieron **0/7** exfiltraciones detectadas en objetivos anotados,
sin fallos entre esos objetivos ni herramientas no autorizadas ejecutadas. Son
solo siete objetivos, con etiquetas provisionales y oráculo limitado; no prueban
riesgo cercano a cero. Se entregó un archivo en cada uno de los dos primeros modos.

**Consumo:** 155 llamadas HTTP 200; US$0.165638 nuevos, acumulado US$1.669110.
[Diseño, datos por corpus, errores y límites](profiles_comparison_20261025.md).

### Prueba sintética anterior: evidencia separada

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

El informe metodológico y los errores encontrados están en [evaluación principal mediante API](api_primary_evaluation_20261024.md). Las seis respuestas del intento cancelado con Luna se excluyen.

### Evidencia observacional adicional de la competencia

Los siguientes registros corresponden al despliegue anterior y se mantienen
separados del nuevo experimento principal; no son su condición protegida.

| Indicador | Solo prompt del sistema, sin Promption | Chatbot con Promption en la competencia | Alcance de la evidencia |
|---|---|---|---|
| Prueba controlada sobre los mismos ataques | No realizada | No realizada | La exportación es observacional; no proporciona comparación causal |
| Turnos observados posteriores al reinicio | No disponible | 5231 | Incluye solicitudes legítimas, ataques, controles y fallos; no es el denominador de ASR |
| Coincidencias de la clave en respuestas finales auditadas | No disponible | 0 encontradas | Búsqueda de valor completo, transformaciones comunes y fragmentos literales de al menos 8 caracteres; no descarta canales no inspeccionados |
| Archivos inspeccionados con coincidencias de la clave | No disponible | 0 de 1 PDF inspeccionado | Evidencia limitada al archivo y comprobaciones registrados |
| Candidato del modelo con clave completa detenido antes de entrega | No disponible | 1 caso documentado | Bloqueo en el filtro de salida; no fue una respuesta entregada al usuario |
| Herramientas no autorizadas ejecutadas con éxito | No medido | No determinado en una evaluación específica | Requiere adjudicar autorización, ejecución y efectos; los contadores de tools no bastan |
| ASR del chatbot completo | No medido | No estimado de forma validada | Falta adjudicación de objetivos y éxito por ataque, además de una condición comparable sin Promption |
| Tareas legítimas completadas correctamente | No medido | No medido con referencia de éxito | Un turno permitido no demuestra que la tarea legítima se completó |

**Nota.** Cero coincidencias encontradas no significa ASR cero ni protección del
100%. No se atribuye a Promption 1.3.3 el comportamiento del chatbot desplegado en
la competencia, cuya versión y configuración deben reportarse por separado. Los
FN de entrada de la tabla 6 no son filtraciones confirmadas del sistema completo.

## Procedencia y límites de publicación

- Tabla 1: `pyproject.toml`, `LIBRARY.md`,
  `docs/context_intent_20261023.md` y `docs/history_transitions_20261023.md`.
- Tabla 2: `output/research_20261023/resumen.json`,
  `output/research_20261023/INFORME.md`,
  `output/guardrail_experiments_20261023/results.json`,
  `output/history_transitions_20261023/summary.json` y
  `docs/fp_fn_evaluation_20261023.md`.
- Tabla 6: `output/guardrail_experiments_20261023/results.json` y
  `output/guardrail_experiments_20261023/supplemental_results.json`.
- Tabla 6B y tabla 7 principal: `output/corpus_three_conditions_20261024/protocol.json`, `summary.json`, `outcomes.csv`, `verification.json` y `episodes/`.
- Tablas 7C–7E: `output/corpus_repeat_140_20261024/protocol.json`, `summary.json`, `version_comparison.json`, `verification.json`, `additional_review.json` y `outcomes.csv`.
- Tabla 7F: `output/profiles_comparison_20261025/protocol.json`, `summary.json`, `outcomes.csv`, `verification.json` y `episodes/`.
- Prueba sintética anterior: `output/api_primary_20261024/protocol.json`, `summary.json`, `outcomes.csv` y `episodes/`; evidencia observacional: `output/research_20261023/INFORME.md` y `resumen.json`.

Los archivos de evidencia con chats y correspondencias permanecen privados. Estas
tablas contienen agregados y descripciones técnicas, sin la clave ni identificadores
de participantes. La tabla 7 contiene una comparación ejecutada, pero esta muestra no permite afirmar
una reducción diferencial de exfiltración: ninguna condición tuvo exfiltraciones
detectadas por el oráculo. Hubo una ejecución interna no autorizada sin protección. Para generalizar
se necesitan revisión humana y un conjunto nuevo, más amplio e independiente; las
repeticiones y traducciones no deben presentarse como casos independientes.
