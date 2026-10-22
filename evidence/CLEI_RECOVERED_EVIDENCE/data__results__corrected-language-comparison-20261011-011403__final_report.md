# Benchmark final: 500 benignos y 500 ataques

Modelo ligero bilingüe reentrenado desde cero. Dataset corregido; semilla 42; umbral ML 0,66.

Particiones: entrenamiento 6540, validación 846, test 1014. Se reservaron 169 filas adicionales, por familias completas, antes de entrenar.

Muestra sin reemplazo: 535 español, 465 inglés; 742 originales y 258 sintéticos; 537 familias.

| Capa | Evaluados | TP | FP | FN | TN | Recall | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Heurística | 1000 | 123 | 3 | 377 | 497 | 24.60% | 0.60% |
| ML ejecutado | 874 | 361 | 4 | 16 | 493 | 95.76% | 0.80% |
| Filtro combinado | 1000 | 484 | 7 | 16 | 493 | 96.80% | 1.40% |
| ML aislado sobre toda la muestra | 1000 | 470 | 5 | 30 | 495 | 94.00% | 1.00% |

Exactitud 97.70%; precisión 98.57%; F1 97.68%; tasa de falsos negativos 3.20%.
Latencia de filtro: media 5.84 ms; p50 4.12 ms; p95 15.82 ms; p99 35.64 ms; máximo 121.67 ms.

## Errores de clasificación

Los 7 falsos positivos proceden de 6 benignos generales y una ficción. Tres son citas educativas detectadas por reglas; cuatro se bloquean en ML. Los 16 falsos negativos corresponden a instruction_override (7), jailbreak (4), role_spoofing (2), credential_exfiltration (2) y safety_bypass (1).
Los 16 ataques no bloqueados quedaron GUARDED; no se observaron decisiones ALLOWED. La generación y Output Guard no se ejecutaron, por lo que no se midió una fuga real.

## Límites

Ejecución local sin LLM: cero llamadas y cero tokens. Alcance, permisos, MCP y Output Guard omitidos. Las etiquetas se revisaron por reglas, no mediante anotación humana exhaustiva.
Sobre los 742 originales: recall 94,07 %, FPR 0,85 %. Las familias sintéticas pueden elevar las métricas; las 1.000 filas no representan 1.000 familias independientes. Esta muestra cambia respecto del benchmark anterior.

Artefactos: benchmark/benchmark_results.csv, benchmark/measured_cases.csv, benchmark/errors.csv, selected_cases.jsonl y comparison.json.

Verificación final: 992 pruebas Python aprobadas, 9 live omitidas y 8 avisos de deprecación; 64 pruebas SDK aprobadas. API y dashboard correctos. Modelo y manifiesto verificados después de las pruebas.
