# Trazabilidad del modelo activo y de la evaluación bilingüe

## Modelo consumido por la aplicación

La configuración versionada activa `model.use_lightweight_ml: true`. En consecuencia, `EnsembleFilter` instancia `LightMLFilter`, que carga `models/lightweight_classifier.pkl`; el archivo está versionado y su SHA-256 es `c4dfb0128d8aa6a91bbe0cc6e81b69b048ee2a1cc49bc072bf8eecc546299efb`.

La comprobación local, sin proveedores ni red, se ejecuta con:

```bash
python scripts/verify_active_layer_configuration.py
```

Verifica el tipo de capa ML, la ruta, el hash del modelo, una inferencia satisfactoria y los umbrales activos. La configuración actual usa 74 reglas heurísticas, umbral bajo 0.33 y umbral alto 0.60.

## Relación con la evaluación de 2026-10-11

El archivo de resultados históricos `corrected-language-comparison-20261011-011403` documenta 97.70% de accuracy con el mismo artefacto ML, pero con umbral 0.66 y un conjunto de reglas de esa ejecución que no fue versionado como snapshot. Por ello, el 97.70% es evidencia histórica por caso, no una afirmación sobre la configuración activa actual.

Al volver a aplicar el código actual sobre aquellos mismos 1,000 casos, con el umbral activo 0.60, se obtienen TP=494, FP=4, FN=6 y TN=496. Es un replay del conjunto ya conocido, no una evaluación independiente y no debe añadirse al artículo como resultado experimental nuevo.

## Evidencia disponible públicamente

- Código de entrenamiento: `scripts/compare_corrected_training.py`.
- Código de decisión: `promption/filter/ensemble_filter.py`, `promption/filter/heuristic_filter.py` y `promption/filter/ml_filter_lightweight.py`.
- Configuración activa y reglas: `config/config.yaml` y `config/heuristics.yaml`.
- Modelo ligero y sus metadatos: `models/lightweight_classifier.pkl` y `models/lightweight_classifier.metadata.json`.
- Datos raw y las traducciones/augmentations incorporadas: `data/raw/`.
- Manifiestos de partición y enlaces de traducción: `data/processed/split_manifest.json` y `data/processed/translation_links.json`.
- Resumen histórico, métricas, denominadores y hashes: `docs/resultados_aleatorios_posteriores.md`.

## Límite de redistribución

El corpus corregido exacto de 8,400 filas, los casos seleccionados y las predicciones completas permanecen fuera del repositorio. Su hash de entrada es `80e23635f2da33281b5e2204944d861ba8a66a5b0ae2358eddd3ba32f7b9bd16`; las salidas locales están identificadas en `docs/resultados_aleatorios_posteriores.md`.

No se republican aún porque NEPI, una fuente incluida, no expone una licencia verificable en su tarjeta pública. Las fuentes con licencia visible incluyen Shomi28 (MIT), deepset (Apache-2.0) y yanismiraoui (Apache-2.0); `jailbreak_llms` declara MIT. Antes de publicar el corpus derivado completo debe verificarse una licencia o permiso redistribuible para NEPI y conservar las atribuciones de todas las fuentes.

La información pública permite inspeccionar el modelo y la cadena de ejecución activa, verificar el artefacto y reconstruir las métricas registradas a partir de los conteos. La reproducción bit a bit de la evaluación histórica requiere además el corpus corregido y el snapshot exacto de reglas de esa fecha.
