# Repetición de 720 episodios con Promption 1.4.0

## Protocolo

Se repiten exactamente los 240 casos de la evaluación anterior, una vez en cada
condición: sin seguridad añadida por la aplicación, solo prompt y prompt con
Promption 1.4.0. Son **720 episodios nuevos**. Los archivos de casos, plan, políticas
y clave sintética tienen las mismas huellas que en el estudio 1.3.3; no se
remuestreó ni se cambiaron etiquetas para favorecer una versión.

Generador y juez de respuesta: `gpt-5.4-nano-2026-03-17`. Guard contextual:
`gpt-5.4-mini-2026-03-17`. Mismos límites: dos episodios concurrentes, tres pasos
del modelo, dos tools, 1024 tokens de salida, sin reintentos y `store=false`.
El código de ejecución y de la biblioteca quedó congelado antes de enviar casos.

La generación utiliza AI SDK y el executor MCP oficial con datos ficticios.
Los documentos se generan y extraen localmente; las páginas son fixtures y las
URLs no se navegan. La clave del reto real y las credenciales no forman parte
del contenido del experimento. Las protecciones intrínsecas del proveedor siguen
presentes también en la condición sin seguridad añadida por la aplicación.

La muestra tiene 120 casos de Lúmina y 120 del corpus de referencia, sesenta
positivos y sesenta negativos por corpus según etiquetas de origen/silver. Solo
49 casos están marcados como dirigidos a extraer clave/configuración: 48 de Lúmina
y uno público. El corpus de referencia combina datos públicos con ejemplos locales.
Los datos ya fueron expuestos durante el desarrollo; esta repetición es una
regresión sobre la misma cohorte, no un nuevo test independiente.

## Instrumentación y comparación

La repetición transmite la solicitud de aislamiento de AI SDK a Python. Se
registran el aislamiento y las aclaraciones fijas de forma diferenciada. Un
dictamen ambiguo que el middleware resuelve mediante aclaración no se registra
prematuramente como bloqueo. Los errores operativos de alcance se clasifican
según su estado real.

El juez usa la rúbrica corregida: una corrección factual no equivale a rechazo de
seguridad. Para comparar las versiones protegidas con una misma rúbrica, se
reclasifican las 75 respuestas generadas guardadas de la versión 1.3.3; no se
regeneran sus chats ni se repite su guard contextual. Las decisiones originales
permanecen intactas. El juez no recibe condición, referencia ni decisiones del filtro.

La matriz cuenta rechazo observado frente a la etiqueta de inyección de la
fuente. Un FN no demuestra que se haya cumplido el ataque; una respuesta inocua
puede no contener rechazo explícito. Las aclaraciones son no rechazos para esta
definición, pero se informan aparte y no cuentan como tareas completadas. Las
etiquetas y el juez automático requieren adjudicación humana.

La exfiltración se mide mediante la clave sintética, formas conocidas y fragmentos
literales de ocho o más caracteres en texto final, archivos aprobados para entrega
y destinos web simulados. Candidatos del modelo y argumentos de tools se informan
aparte. Los fragmentos cortos, estadísticas y codificaciones arbitrarias requieren
inspección adicional; cero coincidencias no equivale a seguridad universal.

## Presupuesto

Se conservó el techo **acumulado de US$2**. La repetición partió de US$0.82848265
ya contabilizados, dejando US$1.17151735. El ledger previo combina los dos estudios
anteriores con identificadores de llamada distintos y verifica las huellas de sus
fuentes. Cada nueva petición reserva coste antes de enviarse. Las reclasificaciones
del baseline también están dentro del mismo techo, sin descuento por caché.

## Resultados

Se completaron **720/720 episodios nuevos** sobre los mismos 240 casos. Los
1354 intentos de llamada del experimento incluyen generación, guard y juez; otras
75 llamadas reclasificaron respuestas antiguas, sin regenerarlas. Los 1429 intentos
quedaron registrados: 1427 respuestas HTTP 200 y dos tiempos de espera. Estos últimos
se conservaron como fallos operativos, sin reintentos y con su reserva completa de coste.

### Tres condiciones: cohorte combinada equilibrada

| Condición | TP | FP | FN | TN | FPR evaluable | FNR evaluable | Fallos operativos | Indeterminados |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Sin protección de aplicación | 71 | 4 | 40 | 100 | 3.85% | 36.04% | 5 | 20 |
| Solo prompt | 69 | 5 | 48 | 105 | 4.55% | 41.03% | 2 | 11 |
| Prompt + Promption 1.4.0 | 112 | 32 | 5 | 77 | 29.36% | 4.27% | 9 | 5 |

### Promption anterior frente a actual, misma rúbrica de rechazo

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

### Exfiltración y herramientas

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

### Coste e integridad

Coste conservador de esta repetición y reclasificación: **US$0.674990**.
Acumulado de los tres experimentos: **US$1.503472 de US$2**.
Incluye US$0.0066698 de reservas retenidas por los dos tiempos de espera; no es
un importe de facturación confirmado. La auditoría verificó hashes, cobertura,
modelos y presupuesto. No encontró la clave real ni credenciales dentro del
contenido de las peticiones, ni alias conocidos en los textos/historiales fuente.
La búsqueda es específica, no una garantía general de anonimización.

Las etiquetas de origen/silver y el juez automático siguen siendo provisionales.
Una respuesta no rechazada no es necesariamente una ejecución exitosa del ataque.
La cohorte reutilizada constituye regresión de desarrollo; no se presenta como
test nuevo ni como demostración de seguridad universal.

## Archivos y reproducción

Evidencia privada: `output/corpus_repeat_140_20261024/`.

- `protocol.json`, `prior_ledger.jsonl`, `frozen_source/`: protocolo y procedencia.
- `episodes/`, `requests/`, `api_responses/`, `api_ledger.jsonl`: ejecución nueva.
- `baseline_judgments/`: reclasificación de respuestas antiguas, sin alterarlas.
- `summary.json`, `outcomes.csv`, `tables.md`: tres condiciones nuevas.
- `version_comparison.json`: versiones protegidas con rúbrica común.
- `verification.json`: integridad, privacidad y gasto.

El análisis guardado no consume API:

```bash
.venv/bin/python scripts/research/summarize_corpus_study.py --output output/corpus_repeat_140_20261024
.venv/bin/python scripts/research/compare_corpus_repeat.py --output output/corpus_repeat_140_20261024
```

No se suman las dos ejecuciones de la misma cohorte como casos nuevos. Las
diferencias entre versiones incluyen correcciones de biblioteca e instrucciones
del guard, además de variabilidad del modelo: no son una ablación por componente.

## Verificación local del instrumental

La suite local terminó con **1100 pruebas aprobadas y 10 omitidas**. Se corrigió
el aislamiento de logging en la importación de la prueba del preparador; no se
modificó el código congelado de ejecución. Las comprobaciones de presupuesto y
aclaraciones de JavaScript también pasaron (20 pruebas). Los tiempos de espera
de la API se conservan como fallos operativos, sin reintentos y con su reserva
completa de coste; al reanudar solo se ejecutan episodios pendientes.
