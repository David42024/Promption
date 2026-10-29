# Promption 1.7.3 — regresión local

Fecha: 25/10/2026, hora de Perú.

## Cambios

- Interpretación de citas analíticas con formulaciones naturales y de instrucciones negadas; una operación afirmativa posterior conserva el veto.
- Aislamiento de preguntas nuevas y completas respecto de ataques antiguos. El texto actual conserva ML, política de riesgo, revisión de alcance y Output Guard; el historial se elimina del contexto enviado al generador únicamente mediante el protocolo de aislamiento.
- Se conserva el clasificador principal. Se incorpora un detector suplementario TF-IDF + ExtraTrees, entrenado con el entrenamiento público y candidatos autónomos depurados de Lúmina. Solo analiza mensajes de usuario; no se aplica su modelo de un turno al historial acumulado o a herramientas.
- Umbral suplementario 0.90 seleccionado en validación: 658 registros públicos y 283 de Lúmina, sin FP adicionales en ninguna de esas dos particiones; 37 VP adicionales. Las etiquetas se conservan y son provisionales.
- Los benchmarks reutilizan el modelo instalado; reentrenar requiere `--retrain` o `--train-only`. Se conserva `--no-train`.
- Dashboard: versión local actual y evaluación histórica con DeepSeek diferenciadas; Output Guard ejecutado se muestra separado del veto de entrada.

## Comparación pareada de la política de entrada

Mismos 5.072 mensajes e historiales antes/después. Los FP/FN pertenecen al veto local: no son medidas de exfiltración ni de respuesta del modelo.

| Conjunto | Evaluables | FP antes → ahora | FPR antes → ahora | FN antes → ahora | FNR antes → ahora | Recall antes → ahora |
|---|---:|---:|---:|---:|---:|---:|
| Públicos test | 658/661 | 47 → 47 | 13.09% → 13.09% | 81 → 78 | 27.09% → 26.09% | 72.91% → 73.91% |
| Lúmina participantes test | 821/821 | 22 → 23 | 5.09% → 5.32% | 166 → 143 | 42.67% → 36.76% | 57.33% → 63.24% |
| Lúmina completo, incluye exposición de entrenamiento | 4411/4411 | 154 → 158 | 7.07% → 7.25% | 1449 → 901 | 64.89% → 40.35% | 35.11% → 59.65% |

## Verificación y límites

- Suite Python: 1.296 aprobadas y 10 omitidas; las pruebas con proveedores de pago no fueron habilitadas.
- Benchmark local: 661 registros, sin llamadas LLM ni ejecución de Output Guard porque no hay respuestas generadas. El visor señala explícitamente esta cobertura.
- Inyección local de fallos de salida: 17 variantes de fuga sintética contenidas y 9 controles legítimos preservados por el middleware. Es una prueba condicionada con generador simulado, no ASR de un modelo real.
- La nueva comparación no consumió API. La batería con DeepSeek de 1.7.2 se conserva como histórica y no se presenta como una evaluación de 1.7.3.
- Se probaron también sustitución completa, SVM calibrada, regularización, proyección latente y voto suave. La sustitución completa aumentó falsos positivos al recibir historiales y fue descartada; los otros experimentos no cumplieron los límites de validación exigidos.
- Las particiones ya habían sido expuestas a diagnósticos. Son resultados de regresión con etiquetas de origen/plata, no estimaciones sobre un nuevo conjunto independiente ni etiquetas humanas adjudicadas.
- Algunos textos públicos etiquetados como benignos contienen órdenes explícitas de ignorar instrucciones. No se modificaron etiquetas ni se retiraron esos registros de la evaluación para mejorar las cifras.
- El detalle de errores operativos, idiomas, matrices de la capa sola y revisión pendiente se conserva en el agregado JSON. Los historiales individuales permanecen privados.
