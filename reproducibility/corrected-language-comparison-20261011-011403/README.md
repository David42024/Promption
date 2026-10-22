# Evidencia pública de la evaluación bilingüe corregida

Este directorio publica los artefactos de bajo riesgo necesarios para auditar el protocolo y sus métricas, sin redistribuir prompts de terceros cuyo permiso no está verificado.

| Archivo | Contenido | SHA-256 |
|---|---|---|
| `comparison.json` | Métricas por partición, idioma y origen; criterios de selección; matriz de la evaluación | `bc7aff20d55c8b2f01bc9ff78340cfd486d0de9f0c7f86f84cc1fb42fdf9915f` |
| `split_manifest.json` | Asignaciones de partición por identificador, fuente y etiqueta | `0a1d3d24caf39e5214d16bfd8eb86e3eb901f2097c86cbebf7c76fd71e85a133` |
| `test-config.yaml` | Configuración de la ejecución histórica; su umbral alto es 0.66 | `79fbc366e239bed6096a902c8e14684ebcca89fea2edee4e001dca38fc391021` |
| `verification.json` | Controles registrados de modelo, manifiesto, muestra y pruebas | `09e144b61d9e33877c92cb96dfdc243a9fe9065b1b5bab270f56b20cb9757639` |
| `label_review_proposals_20261010.csv` | Propuestas de revisión, identificadas por hash de prompt | `c8371e919f1e34bc9ab9700f781370e795644c4e4eadc33ddd51a21a44ea1098` |

El corpus de entrada de la evaluación tiene SHA-256 `80e23635f2da33281b5e2204944d861ba8a66a5b0ae2358eddd3ba32f7b9bd16`; el modelo activo tiene SHA-256 `c4dfb0128d8aa6a91bbe0cc6e81b69b048ee2a1cc49bc072bf8eecc546299efb`.

Para revisar la capa usada por la aplicación actual, ejecutar desde la raíz del repositorio:

```bash
python scripts/verify_active_layer_configuration.py
```

El resultado histórico de 97.70% fue obtenido con umbral 0.66. La configuración actual usa 0.60 y reglas posteriores, por lo que no debe esperarse la misma matriz de confusión. Véase `docs/reproducibilidad_resultados_bilingues.md` para la separación entre evidencia histórica y comportamiento actual.
