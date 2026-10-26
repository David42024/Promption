# Promption 1.6.0: contexto, intención y revisión

Cambios locales del 25/10/2026. No se publicaron paquetes ni se desplegó la app.

## Cinco controles implementados

| Requisito | Comportamiento | Evidencia |
|---|---|---|
| Separar decisiones | `assessments.injection`, `.scope` y `.authorization` tienen estado, motivo, origen y lista de evaluaciones. No ejecutado se informa como `not_evaluated`. Un permiso denegado no se etiqueta automáticamente como inyección. Los errores conservan evaluaciones anteriores. | `promption/assessments.py`, `guard.py`, API; `packages/ai-sdk/src/assessments.js`, middleware y pruebas `decision-axes.test.js` |
| Aclarar datos faltantes | Dictamen `UNCERTAIN/missing_information` compatible y sin ataque identificado devuelve una frase fija. Las referencias incompletas sin antecedente tienen una alternativa local conservadora si no hay evaluador. Sin tools ni generación. No reemplaza errores del evaluador. | `scope.py`, `test_contextual_decisions.py`, SDK con `generateText` y `streamText` |
| Revisar señales débiles | Las reglas amplias de menciones, autoridad y contacto llevan `action: review`; las reglas concluyentes mantienen `block`. La revisión de contexto se exige cuando corresponde y toda salida generada sigue protegida. | Heurística, ensemble, API, transportes y pruebas de flags malformados |
| Conservar procedencia | Solo citas analíticas de usuario bien delimitadas generan una vista de instrucciones. El original llega al evaluador y generador. Si luego se pide obedecer o ejecutar la cita, se recupera como evidencia de instrucciones. Tools no obtienen esa interpretación de usuario. | `evidence.py`, `conversation_guard.py`, pruebas de adopción y flujo HTTP real |
| Calibrar ES/EN | 96 ejemplos difíciles, 48 ES y 48 EN; selección del umbral de veto con la partición de calibración. Scores declarados como `uncalibrated_detection_score`. | `data/calibration/`, `scripts/research/calibrate_hard_cases.py` |

Los estados posibles son `allowed`, `denied`, `uncertain`, `not_evaluated` y
`error`. Los motivos de cada eje son independientes. Un evaluador semántico nunca
otorga permisos de servidor. Los vetos concluyentes se combinan mediante OR;
ni una cita ni una opinión semántica favorable anulan un veto ML concluyente.

## Configuración actual

| Perfil | Incertidumbre de entrada | Ambigüedad de alcance compatible | Datos de negocio faltantes, sin ataque |
|---|---|---|---|
| `conversational` | Revisión | Aclaración fija; puede admitir intención desconocida | Aclaración fija |
| `balanced` | Revisión | Aclaración fija con intención conocida compatible | Aclaración fija |
| `strict` | Revisión | Bloqueo | Aclaración fija |

Las excepciones de aclaración siguen exigiendo evidencia válida y no sensible,
sin herramientas propuestas ni formato JSON. Un timeout, respuesta inválida,
ataque identificado o dato protegido no se convierten en aclaración. La pregunta
es fija: no es una generación autorizada. `allowed` permanece `false` y exige
Output Guard antes de entregarse. Un servidor puede seleccionar explícitamente
`input_uncertainty='block'` / `inputUncertainty: 'block'`.

`requires_scope_review` y `requires_output_guard` son contratos distintos. En
Python se configura `ContextScopeGuard` y en AI SDK `scopeEvaluator` con
`createContextEvaluator`. Cuando la primera bandera es verdadera y no existe un
evaluador, el pipeline rechaza con 503 antes de generar. `check_conversation` y
`/filter` son controles diagnósticos de detección; no sustituyen el pipeline de
alcance, ACL y revisión de salida.

El endpoint diagnóstico del Chat Service `/ai/guard` usa explícitamente
`AsyncGuardPipeline(defer_scope_review=True)`: devuelve la revisión pendiente al
middleware, que ejecuta el evaluador o rechaza si no está configurado. No genera
contenido en ese endpoint. Esta delegación la configura el servidor y no es un
campo aceptado del usuario; el pipeline Python conserva el bloqueo predeterminado.

La interpretación de citas es conservadora: hasta 20 000 caracteres de entrada,
entre una y ocho citas, máximo 8192 caracteres por cita, marco de análisis
reconocido y sin una instrucción operativa adicional. Formatos ambiguos se
evalúan como texto completo. No garantiza comprender cualquier forma de cita.

## Calibración exploratoria

Sin reentrenar pesos. Clasificador activo: TF-IDF + regresión logística; no se
descargó ni activó DeBERTa/BERT. SHA-256 de pesos sin cambios:
`81f0ae6c2d017617c449cd6e53c0a384613493056eb9034a4152b60c79de7bfa`.

El corpus tiene 64 negativos y 32 ataques, distribuidos por idioma y familia en
calibración y validación. Se compararon umbrales 0.66, 0.75, 0.80, 0.85, 0.90,
0.95 y 0.99; el selector consultó solo calibración y eligió **0.85** al minimizar
FP y elegir el menor umbral con FPR ≤10%, recall de veto ≥75% y ningún ataque
en pase directo. La nueva configuración empaquetada coincide con la del repo.

| Versión / partición | TP veto | FP veto | FN sin veto | TN | FPR |
|---|---:|---:|---:|---:|---:|
| 1.5.0 / validación, 48 casos | 16 | 8 | 0 | 24 | 25% |
| 1.6.0 / calibración, 48 casos | 16 | 0 | 0 | 32 | 0% |
| 1.6.0 / validación, 48 casos | 15 | 0 | 1 | 32 | 0% |

El único ataque sin veto en validación quedó en revisión obligatoria, no en pase
directo. Los 32 negativos de validación también quedaron en revisión: cero vetos
indebidos no demuestra tareas legítimas completadas. Este corpus es sintético,
con etiquetas de desarrollo y familias/paráfrasis compartidas; se inspeccionaron
errores durante el desarrollo de reglas. No es una evaluación ciega ni una
estimación independiente de generalización. El selector no consulta validación,
pero eso no elimina la exposición de desarrollo. No interpretar un score 0.85
como 85% de probabilidad de ataque.

Se mantienen `ml_probability`, `confidence` y las columnas CSV anteriores por
compatibilidad. El nuevo `score_kind` aclara la interpretación; cambiar el nombre
histórico de un campo no convertiría el score en una probabilidad calibrada.

Las [720 ejecuciones de la muestra Lúmina/pública](local_profiles_sample_20261025.md)
son un control adicional distinto y conservan sus propios resultados y límites.
La disminución de vetos produce más revisiones: no se oculta esa carga ni se
declara una mejora de ASR o exfiltración sin un modelo real.

## Verificación

Suite completa: **1196 pruebas Python aprobadas, 10 omitidas**, y **140 pruebas
nativas de AI SDK aprobadas**; tipos TypeScript sin errores. Benchmark sin LLM ni
reentrenamiento: 661 registros con salidas en carpeta separada. API y dashboard
respondieron 200; el dashboard también se ejecutó en una sesión AppTest sin
excepciones. Wheel y tarball 1.6.0 se importaron fuera del checkout, con defaults
empaquetados verificados. Los pesos y el CSV de benchmark anterior se conservaron.

Pruebas Python de los cinco controles, pruebas nativas del middleware y tipos.
`packages/ai-sdk/scripts/verify-context-flow.mjs` se ejecutó contra una FastAPI
efímera real en loopback con credenciales sintéticas y modelos simulados de AI
SDK: los tres perfiles conservaron citas, pidieron contexto, revisaron salida,
vetaron la inyección de tool y no ejecutaron la herramienta sin permiso. Sin
evaluador requerido se bloqueó antes de generar. No hubo llamadas externas de IA.
