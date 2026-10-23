# Promption 1.2.0: estrategias de guardrails y comparación local

## Qué aportan los sistemas revisados

| Sistema / fuente primaria | Estrategia útil | Aplicación en Promption |
|---|---|---|
| [NeMo: tipos de rails](https://docs.nvidia.com/nemo/guardrails/latest/about-nemo-guardrails-library/rail-types) | Separar entrada, recuperación, diálogo, herramientas y salida | Conservar las barreras de permisos, contexto y salida aunque mejore el detector de entrada |
| [Meta: Prompt Guard 2](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-22M) | Adaptación al dominio, segmentación de entradas largas y evaluación multilingüe | Comparar reentrenamiento local y ventanas; el 86M es candidato para una futura comparación en español |
| [LLM Guard: PromptInjection](https://protectai.github.io/llm-guard/input_scanners/prompt_injection/) | Modos de coincidencia y revisión por segmentos | Inspeccionar texto completo y ventanas solapadas, conservando el mayor riesgo |
| [Guardrails AI: validadores](https://guardrailsai.com/guardrails/docs/concepts/validators) | Validadores componibles y resultados explícitos | Componer vetos independientes, sin permitir que un detector absuelva el bloqueo de otro |

No se copiaron cifras de esos proveedores como si fueran resultados de Promption.
La ficha de Meta indica que el 86M tiene base multilingüe y que el 22M presenta
mayor diferencia de rendimiento fuera del inglés. Sus etiquetas se refieren a
intentos explícitos de sobrescribir instrucciones: no sustituyen una política de
acceso a secretos o archivos de una empresa.

La [documentación de NeMo sobre perplejidad](https://docs.nvidia.com/nemo/guardrails/latest/configure-guardrails/guardrail-catalog/jailbreak-protection)
advierte falsos positivos adicionales fuera del inglés. No se incorporó esa heurística.
El [repositorio de LLM Guard](https://github.com/protectai/llm-guard) está archivado
desde el 9 de julio de 2026; se tomó su estrategia como referencia sin añadirlo
como dependencia nueva. No se instalaron ni evaluaron aquí los modelos externos de
Meta o NVIDIA. Todas las pruebas de este informe se hicieron localmente con sklearn.

## Diagnóstico de los datos

- El corpus existente tiene 6424 registros en inglés y 1399 en español según sus
  marcadores de idioma. La competencia tiene otro dominio y mucho lenguaje informal.
- Los candidatos silver estaban divididos por participante y familia. Se conservaron
  esas divisiones, se excluyeron 16 textos con marcadores de redacción y se comprobó
  solapamiento exacto/por trigramas con el corpus anterior.
- Quedaron 822 candidatos para entrenamiento, 60 para validación y 179 para prueba.
  La validación solo incluye **7 negativos**: no permite estimar con precisión un
  límite de falsos positivos. Se añadió validación cruzada de tres folds sobre
  componentes conectados de participantes y familias, dentro del entrenamiento.
- El entrenamiento anterior se reconstruyó por grupos del manifiesto: 3092 filas.
  Dos filas del CSV actual no tienen grupo asignable al manifiesto y se excluyeron.
  No se inventó su partición. Validación y prueba anteriores conservaron 658 y 661 filas.

La búsqueda de duplicados usa igualdad normalizada o Jaccard de trigramas de palabras
>= 0.8; no prueba ausencia de paráfrasis semánticas. Los hashes, IDs seudonimizados,
particiones y exclusiones están en el directorio privado del experimento.

## Estrategias probadas

1. Modelo original y umbral actual 0.66, con las reglas de la versión 1.1.1.
2. Calibrar únicamente el umbral, sin reentrenar.
3. Adaptar TF-IDF + LogisticRegression al entrenamiento anterior y a los candidatos
   silver, explorando pesos 0.25, 1 y 2 para la competencia.
4. Comparar texto completo contra texto completo más ventanas de 500 caracteres,
   con 100 de solapamiento. Se mantienen todas las ventanas y el texto completo.
5. Conservar el detector original y añadir el adaptado con un umbral independiente.

Los modelos se ajustaron únicamente con entrenamiento. La selección inicial usó
validación cruzada agrupada; el umbral final se seleccionó con las particiones de
validación. La selección impuso un presupuesto de falsos positivos por corpus,
evitando esconder errores de un dominio dentro de un promedio global.

Ganó el adaptado con peso 2 y ventanas, con umbral 0.71. Sin embargo, reemplazar
el original empeoró su corpus anterior. Por eso se probó después la composición
OR: umbral original 0.66 y umbral complementario 0.82, seleccionado en validación.
Esta composición conserva por construcción cada veto original; puede añadir otros.
Eso no garantiza conservar la tasa de falsos positivos en tráfico futuro.

## Resultados en mensajes individuales reservados de la competencia

| Estrategia | TP | FP | FN | TN | Total |
|---|---:|---:|---:|---:|---:|
| Original 1.1.1 | 46 | 2 | 84 | 47 | 179 |
| Solo calibrar el umbral | 49 | 3 | 81 | 46 | 179 |
| Reemplazar por adaptado y ventanas | 93 | 1 | 37 | 48 | 179 |
| Original OR detector complementario | 88 | 2 | 42 | 47 | 179 |

Con el complemento, la detección pasó de 46/130 a 88/130 positivos de referencia
provisional. Los FN se redujeron a la mitad en esta muestra; no es una afirmación
de reducción del 50% de ataques exitosos ni una estimación validada para producción.

## Regresión en el corpus anterior

| Estrategia | TP | FP | FN | TN | Total |
|---|---:|---:|---:|---:|---:|
| Original 1.1.1 | 245 | 48 | 57 | 311 | 661 |
| Solo calibrar el umbral | 245 | 48 | 57 | 311 | 661 |
| Reemplazar por adaptado y ventanas | 232 | 48 | 70 | 311 | 661 |
| Original OR detector complementario | 247 | 48 | 55 | 311 | 661 |

El perfil complementario es la alternativa conservadora explorada: mejora la
competencia sin perder vetos del modelo original. El perfil de reemplazo queda
separado para estudiar el intercambio entre especialización y generalización.

## Límites científicos

Las etiquetas siguen siendo **silver, no gold humano**. El conjunto de prueba de
la competencia se excluyó del ajuste del clasificador y la selección inicial, pero
ya había aparecido en diagnósticos de reglas anteriores. La composición OR fue un
seguimiento decidido después de observar los resultados del reemplazo. Sus cifras
son **exploratorias**, no una nueva prueba ciega independiente. Se conservan los
protocolos y la secuencia temporal en lugar de presentar ese seguimiento como
preregistrado desde el principio.

No se reprodujeron aquí el historial completo, respuestas LLM, páginas externas ni
efectos de herramientas. Un FN de entrada no acredita filtración; una negativa del
modelo o los guards posteriores pueden impedirla. Para publicación hace falta una
cohorte nueva, revisión humana, evaluación de conversaciones de varios turnos y medición de utilidad y
filtración real. Estos resultados tampoco son comparables directamente con las
cifras de 1238 mensajes del informe anterior: el denominador es distinto.

## Cambios en la librería

- `score_texts`: inferencia por ventanas en lotes, sin truncar texto y con validación
  de probabilidades. Los artefactos antiguos conservan su inferencia original.
- `choose_threshold`: calibración con presupuesto de FP por segmento de validación.
- Entrenamiento con pesos por ejemplo y exclusión de etiquetas desconocidas/no binarias.
- `LightMLFilter.from_artifact`: instancias independientes para evitar que el singleton
  de un modelo cambie el archivo o el umbral de otro.
- `EnsembleFilter(additional_filters=...)`: cada detector conserva su umbral y su veto.
  La API y el guard conversacional registran la capa complementaria. Un fallo de un
  detector complementario configurado detiene la petición como error de servicio.
- `ensemble.additional_classifiers` permite configurar el complemento por archivo.
  El modelo general y la configuración por defecto permanecen intactos.

Ejemplo reusable:

```python
from promption.filter.ensemble_filter import EnsembleFilter
from promption.filter.ml_filter_lightweight import LightMLFilter

complement = LightMLFilter.from_artifact("/ruta/adapted_classifier.pkl", threshold=0.82)
protection = EnsembleFilter(additional_filters=[complement])
```

El modelo y los perfiles están en el directorio local **privado**
`output/guardrail_experiments_20261023/`:

- `supplemental_config.yaml`: original más complemento; opción conservadora.
- `experimental_config.yaml`: reemplazo por el adaptado; tiene regresión en el corpus anterior.
- `results.json`, `supplemental_results.json`, `runtime_replay.json`: resultados y verificación.
- `frozen_splits.json`, `provenance.json`, `protocol.json`: trazabilidad.

Para probar el perfil complementario en el servicio local:

```bash
PROMPTION_CONFIG_FILE="$PWD/output/guardrail_experiments_20261023/supplemental_config.yaml" \
  uvicorn promption.api.main:app --port 8000
```

Los perfiles requieren el artefacto privado en la ruta configurada. No se enviaron
chats a proveedores, no se usó OpenAI, no se subieron credenciales y no se desplegó
el experimento. Los pesos no se incluyen automáticamente en el wheel público.

## Reproducción

```bash
python scripts/research/guardrail_strategies.py \
  --research output/research_20261023 \
  --output output/guardrail_experiments_20261023_nuevo
python scripts/research/conservative_extension.py \
  --research output/research_20261023 \
  --experiment output/guardrail_experiments_20261023_nuevo
```

El primer script exige una carpeta de salida nueva para no sobrescribir resultados.
La activación del perfil es explícita; no se reemplaza automáticamente el modelo
original con etiquetas pendientes de validación humana.

## Verificación de la integración

- 963 pruebas Python aprobadas y 10 omitidas; 68 pruebas del SDK aprobadas y tipos sin errores.
- Reproducción con `EnsembleFilter` real y el perfil YAML: 840 casos, mismos resultados
  que el cálculo offline y ningún veto del modelo original perdido.
- Wheel 1.2.0 construido e instalado en un directorio aislado.
- La prueba valida detección de entrada y contratos de integración; no mide ASR real
  ni acredita el rendimiento de un modelo externo no ejecutado.
