# Resultados aleatorios posteriores para el artículo

Esta nota preserva los resultados de la evaluación posterior al snapshot histórico citado por el artículo. Es una evaluación complementaria y no sustituye las tablas basadas en el corpus de 5,872 entradas.

## Resultado del filtro combinado

La muestra aleatoria equilibrada contiene 1,000 entradas: 500 ataques y 500 entradas benignas. El filtro combinado produjo la siguiente matriz de confusión:

| TP | FP | FN | TN | Accuracy | Precisión | Recall | F1 | FPR |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 484 | 7 | 16 | 493 | 97.70% | 98.57% | 96.80% | 97.68% | 1.40% |

El clasificador ML evaluado de forma aislada sobre esa muestra produjo TP=470, FP=5, FN=30 y TN=495: accuracy 96.50%, precisión 98.95%, recall 94.00% y FPR 1.00%.

## Protocolo y evidencia

- Fecha de la ejecución: 2026-10-11.
- Corpus corregido bilingüe: 8,400 filas.
- Separación declarada: entrenamiento 6,540, validación 846 y prueba 1,014; la muestra medida contiene 1,000 casos equilibrados sin reemplazo.
- La verificación registrada informa cero solapamientos de familias entre entrenamiento, validación y muestra; 1,000 prompts sin duplicados; modelo y manifiesto verificados.
- La muestra contiene 742 casos originales y 258 sintéticos, repartidos en 537 familias. Las etiquetas fueron auditadas por reglas, sin certificación humana independiente por caso.
- Es una evaluación de clasificación de entrada sin proveedor LLM: cero llamadas y cero tokens. No mide por sí sola Conversation Guard, Output Guard, Scope, RBAC ni Tool Guard en conversaciones reales.

Los artefactos de ejecución permanecen locales porque `data/results/` está excluido del control de versiones. Para revisar la evidencia completa se requieren los archivos con estos hashes SHA-256:

| Artefacto local | SHA-256 |
|---|---|
| `final_report.md` | `63604d2eb108bd25acfe128e16905c5eb5ea1958860d6eaaddecbaF374924c9f` |
| `comparison.json` | `bc7aff20d55c8b2f01bc9ff78340cfd486d0de9f0c7f86f84cc1fb42fdf9915f` |
| `benchmark/measured_cases.csv` | `74cfe977aafd02402c74fdcdd953302918dced0902b647015fbe68aef233e033` |

## Uso adecuado en el artículo

Puede describirse como una evaluación posterior separada: el filtro combinado obtuvo 97.70% de accuracy, 98.57% de precisión, 96.80% de recall y 1.40% de FPR en una muestra aleatoria equilibrada de 1,000 casos. No debe presentarse como una mejora directamente comparable a la evaluación principal, porque cambiaron el corpus, la curación, la composición sintética y el protocolo.

El replay V4 de 99.00% se mantiene como resultado histórico sobre casos conocidos, no como estimación independiente de generalización.
