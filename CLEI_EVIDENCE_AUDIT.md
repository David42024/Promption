# Auditoría de evidencia científica — Promption / CLEI

Fecha de inspección: 2026-10-13. La inspección fue de solo lectura: no se ejecutaron experimentos, servidores, entrenamientos ni llamadas a proveedores, y no se modificaron resultados originales.

## Resultado ejecutivo

No se recuperó evidencia suficiente para afirmar que los ocho experimentos del manuscrito se ejecutaron en este checkout. Se recuperaron artefactos históricos de otros protocolos, el E1 sintético y un E2 parcial, pero no el paquete de evaluación CLEI con sus predicciones, métricas y cinco particiones leave-one-source-out.

El dataset procesado actual contiene 8.400 filas y tiene fuentes adicionales (traducciones, plantillas, locales y sintéticas). Su `split_manifest.json` registra 6.540 train, 846 validation y 1.014 test. Por tanto, no coincide con el corpus CLEI descrito de 5.872 filas ni permite recuperar su distribución publicada sin un manifiesto o corpus original adicional.

## Archivos localizados

| Artefacto | Estado | Ruta |
|---|---|---|
| Harness CLEI `evidence/evaluate_article.py` | NO LOCALIZADO | — |
| `metrics.csv`, `predictions.csv`, `corpus_manifest.csv`, `decision_matrix.csv` CLEI | NO LOCALIZADO | — |
| Split manifest actual | PARCIAL | `data/processed/split_manifest.json` |
| Datos procesados actuales | PARCIAL / CONTRADICTORIO con 5.872 | `data/processed/training_data.csv`, `reviewed_training_data.csv` |
| Overrides y cuarentena | LOCALIZADO | `data/processed/label_overrides.csv`, `data/processed/quarantine.csv` |
| Análisis científico histórico disponible | PARCIAL | `data/results/scientific-v9-historical-final-20261012/` |
| Resultados E1 sintéticos | LOCALIZADO, protocolo distinto | `data/results/synthetic-benchmark-v9-final/e1_results/` |
| Resultados E2 | PARCIAL, 64/400 recorridos | `data/results/synthetic-benchmark-v9-final/e2_results/` |
| Corrección V4 y replay conocido | LOCALIZADO, no independiente | `data/results/v4-full-chat-20261010-232722/` |

El directorio científico histórico contiene `layer_metrics.csv`, `layer_evidence.csv`, `family_metrics.csv`, `latencies_by_stage.csv`, `paired_results.csv`, `summary.json` y `final_report.md`, pero documenta un ensayo de Chat de 40 casos por brazo, no las ocho particiones CLEI solicitadas.

## Corpus de 5.872 registros

**NO VERIFICADO / CONTRADICTORIO.** El CSV actual tiene 8.400 filas. El conteo por fuente incluye `jailbreak_llms` 1.590, `Shomi28` 914, `deepset` 363, `NEPI` 512 y `yanismiraoui` 23, además de fuentes adicionales. No coincide con la tabla 3.201 benignos + 2.671 ataques del manuscrito. No se encontró un corpus CLEI separado, un archivo de deduplicación que produzca 5.872 filas ni un manifiesto SHA-256 correspondiente.

Hashes actuales:

| Archivo | SHA-256 |
|---|---|
| `data/processed/training_data.csv` | `4dd66ecad309eb5c2b137e0ac9a84c371c96f05d46b928ae10924e66c4e2303e` |
| `data/processed/split_manifest.json` | `0a1d3d24caf39e5214d16bfd8eb86e3eb901f2097c86cbebf7c76fd71e85a133` |
| `data/processed/label_overrides.csv` | `0347b180b30a4382c6a5ad6030f6630685380754b6b802d6aeeafa7d3be8d108` |
| `data/processed/quarantine.csv` | `8a32264b2f22e7c05ccaef40e7d69e5051b1f709d2bd8e6f324877c25559211` |

## Ocho experimentos y matrices

| Afirmación | Estado | Evidencia |
|---|---|---|
| Semillas 42, 43 y 44, 4.697/1.175 | NO LOCALIZADO | Solo se encontró manifest actual seed 42 con 6.540/846/1.014 |
| LOSO NEPI, Shomi28, deepset, jailbreak_llms, yanismiraoui | NO LOCALIZADO | No hay métricas/predicciones/manifiestos CLEI por fuente |
| Matriz seed 42 99/49/435/592, 443/19/91/622, 448/64/86/577, 445/52/89/589 | NO VERIFICADO | No se encontró registro individual que la produzca |
| Latencias 600, mediana 4,33 ms, p95 21,69 ms, media 7,01 ms | NO LOCALIZADO | Las latencias encontradas pertenecen a otros protocolos |

El archivo `data/results/corrected-language-comparison-20261011-011403/final_report.md` sí contiene matrices históricas de otro protocolo (heurística 123/3/377/497, ML aislado 470/5/30/495, ensemble 484/7/16/493). No deben atribuirse al manuscrito CLEI.

## Código y commit

El commit `8e13d8cffb80e79139758efea54687f3f353c275` no existe en el historial Git local; no se hizo checkout ni cambio de rama. El código actual configura TF-IDF + Logistic Regression en `config/config.yaml`, y los umbrales actuales son 0,60. Esto no prueba que fueran la configuración del artículo. La inspección encontró reglas heurísticas en `config/heuristics.yaml`, pero no una evidencia versionada que demuestre exactamente 60 reglas maliciosas y 5 benignas para el commit citado ni una implementación CLEI verificable de `decide_pipeline_action`.

## Splitter e índices

No se localizó un harness CLEI ni una ejecución que demuestre los 199 registros excluidos. El `split_manifest.json` actual contiene identificadores y fuentes, pero su existencia no demuestra el bug histórico ni su corrección. La afirmación del splitter queda **NO LOCALIZADA**.

## Paquete recuperado

Se creó `evidence/CLEI_RECOVERED_EVIDENCE/` con copias pequeñas de los manifiestos, overrides, cuarentena, código de configuración relevante, informes y resúmenes encontrados, más `INVENTORY_AND_HASHES.json`. Se excluyeron `.env`, claves, modelos binarios, dependencias, historiales de Chat y datasets completos cuando no eran necesarios para localizar la evidencia.

## Recomendación

La evidencia permite redactar una sección de limitaciones y separar los protocolos históricos, E1 sintético y E2 parcial. No permite presentar como verificados los ocho experimentos CLEI, el corpus de 5.872 filas, las matrices seed 42 ni las latencias de 600 predicciones. Para una afirmación verificable se necesita recuperar el commit citado o un paquete que contenga las cinco predicciones LOSO, las tres particiones, el corpus deduplicado, los manifiestos y los logs de entrenamiento/evaluación.
