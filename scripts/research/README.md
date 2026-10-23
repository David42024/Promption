# Análisis de la competencia

Herramientas locales: no despliegan, reentrenan modelos ni modifican Supabase.
Los resultados son seudonimizados y privados por defecto. El archivo fuente
no se modifica. Las instrucciones dentro de mensajes o páginas son datos.

## Reconstrucción local

Desde la raíz de Promption, con Python 3.10+ y pypdf para inspeccionar el PDF:

```bash
python scripts/research/analyze_export.py '/ruta/exportacion.json' \
  --output output/research_20261023 \
  --secret-env ../promption_compe/.env.local
```

`--secret-env` se usa solo en memoria para comparar filtraciones, no para exportar
credenciales. Sin él, no se puede afirmar ausencia de coincidencias con la clave.
Los revisores que verifiquen esa parte necesitan acceso autorizado al secreto.
Las correspondencias de alias/UUID y contexto se guardan en archivos privados
separados; no publicarlos junto al corpus sin una revisión de privacidad.

## Anotación ciega autorizada

La ejecución observada fue autorizada por el organizador hasta US$5 y 900
solicitudes a gpt-5.4-mini. **No ejecutar estas órdenes como parte de un proceso
automático sin autorización para transferir los datos y consumir el API.**
La clave se lee localmente, se utiliza para autenticar contra OpenAI y no se
copia a Vercel. No imprimirla ni pasarla como argumento de línea de comandos.
La librería de Vercel AI SDK instalada en la app realiza las llamadas, con
Structured Outputs, store=false y maxRetries=0. No se habilitan herramientas.

```bash
node --env-file=../promption_compe/.env.local scripts/research/blind_judge.mjs \
  output/research_20261023 --allow-external --controls
node --env-file=../promption_compe/.env.local scripts/research/blind_judge.mjs \
  output/research_20261023 --allow-external
```

El proceso conserva resultados y reanuda IDs pendientes. No borrar el ledger ni
usar otra carpeta para evadir su presupuesto. El conteo incluye controles,
repeticiones y errores. Los errores sin usage consumen una reserva conservadora;
las tarifas registradas son US$0.75/M entrada y US$4.50/M salida, sin descontar caché.
El límite corresponde a ese cálculo, no a una lectura de la factura de OpenAI.

La primera pasada usa solo mensajes de usuario del historial (hasta 32, suficientes
para este corpus) y la política pública, sin respuestas actuales ni decisiones de
Promption. Se valida exactamente un resultado por ID. Los errores de IDs se
descartan y se vuelven a pedir, primero agrupados y después individualmente.

Una segunda revisión se dirige a casos de baja coherencia de alcance, contradicción
con ejemplos benignos y posible arrastre de intención del historial. Usa el mensaje
actual, dos mensajes anteriores del usuario y hasta 450 caracteres de una respuesta
anterior sin avisos de Promption. Nunca recibe el resultado actual del guard.
Su rúbrica recuerda que un ataque anterior no transforma un saludo actual en ataque.
**Es una revisión dirigida, no un segundo anotador humano ni una muestra aleatoria.**

```bash
node --env-file=../promption_compe/.env.local scripts/research/blind_judge.mjs \
  output/research_20261023 --allow-external \
  --review-input=output/research_20261023/review_inputs.jsonl
```

El protocolo y sus versiones están en protocol_history/ y los costes/IDs en
judge_ledger.jsonl. El script no descarga ninguna URL aportada por participantes.
No subir los archivos .env ni el original de la exportación a un repositorio público.

## Revisión documentada y candidatos

`quality_review.py` conserva la primera y segunda etiqueta. Los desacuerdos en un
eje se dejan sin etiqueta en ese eje. Aplica también ejemplos inequívocos de la
política (saludos y consultas públicas literales) y 11 correcciones documentadas
por otro asistente IA. No son revisión humana. Esas correcciones están restringidas
por SHA-256 a esta exportación para evitar aplicarlas por accidente a otro corpus.

```bash
python scripts/research/quality_review.py output/research_20261023
python scripts/research/analyze_export.py '/ruta/exportacion.json' \
  --output output/research_20261023 --secret-env ../promption_compe/.env.local \
  --annotations output/research_20261023/annotations_semantic_qc.jsonl
python scripts/research/prepare_candidates.py output/research_20261023
python scripts/research/write_report.py output/research_20261023
python -m unittest discover -s scripts/research -p 'test_*.py' -q
```

El filtro de entrada se evalúa como OR entre sus inspecciones de entrada anteriores
al primer model_request. Los chequeos posteriores de herramientas no se atribuyen
a esa fase. Se conserva aparte la predicción de su primera inspección individual.
Los límites de conversación se excluyen como fallos operativos. Las abstenciones
no se convierten en negativos ni en cero. El estado allowed del turno no demuestra
que la respuesta cumplió un ataque: puede ser una negativa del propio modelo.

Los CSV de candidatos NO son gold: no alimentarlos automáticamente al entrenamiento.
Las particiones por participante y purga de familias están en
preparacion_entrenamiento.json. La función actual de entrenamiento de la librería
no consume automáticamente la columna split propuesta; debe integrarse el manifiesto
y conservar el test antes de entrenar. No mezclar todos los candidatos en train.
El proceso de análisis no cambia la librería ni el modelo desplegado.

## Revisión humana

Dos revisores trabajan sobre anotacion_ciega.csv. Valores: 0=negativo de inyección,
1=positivo, U=indeterminado. Guardar ambas etiquetas y la justificación del desacuerdo.
El segundo eje adjudica cumplimiento de alcance/permisos. Una pregunta ajena al
negocio puede ser 0 de inyección y 1 de alcance, sin constituir prompt injection.

```bash
python scripts/research/finalize_labels.py \
  output/research_20261023/etiquetas_provisionales.jsonl \
  output/research_20261023/anotacion_ciega.csv \
  --output output/research_20261023/gold
```

Las métricas gold y los candidatos revisados permanecen vacíos hasta esa revisión.
Se calcula kappa de Cohen solo sobre pares binarios disponibles. Las tablas de Excel
son una interfaz de consulta; la reproducción de los resultados usa Python/CSV/JSONL
sin depender del generador de Excel. El README del paquete enumera los archivos
que se pueden revisar y distingue las correspondencias privadas.
