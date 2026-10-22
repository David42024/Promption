# Promption V4 — Correcciones conservadoras de detección y auditoría

## Alcance y origen

Se trabajó sobre `promptionsystem.rar` (RAR5, 1,586 entradas, con registros históricos y archivos multimedia). Este paquete extrae **solo el código fuente de `promption/`, la configuración `config/` y algunos datasets y metadatos necesarios**: no contiene los 1.2 GiB de multimedia, historiales ni todos los artefactos del entorno. El archivo suministrado no incluye `models/lightweight_classifier.pkl` ni un directorio de tests del proyecto. No se hizo ninguna llamada al proveedor LLM ni se reentrenó un modelo.

El análisis de sensibilidad a umbral es un **replay del benchmark conocido** con las probabilidades ML previamente registradas. No es test independiente. La clasificación del benchmark usa etiquetas aún pendientes de adjudicación; no debe confundirse con seguridad de extremo a extremo.

## Archivos fuente modificados

| Ruta | Modificación | Motivo |
|---|---|---|
| `config/config.yaml` | `ensemble.decision_high_threshold`, `classification.ml_malicious_threshold` y `model.confidence_threshold` pasan de `0.66` a `0.60`. | Prueba de sensibilidad reportada por el usuario; evitar decisiones diferentes entre ML standalone y ensemble. **Candidato sujeto a validación independiente**, no mejora garantizada. |
| `promption/resources/config.yaml` | Los mismos tres umbrales, conservando el resto de configuración propia del paquete. | Evitar divergencia de umbrales en instalación distribuida. |
| `config/heuristics.yaml` | Cinco reglas: `forget_previous_instructions_context_en` (media), `dan_persona_signal_bilingual` (media), `dual_persona_bypass_bilingual` (alta, requiere orden de responder + oposición), `evil_roleplay_context_signal` (media), `concealed_credential_exfiltration_en` (alta, exige ocultamiento explícito). | Capturar formulaciones en ES/EN sin bloquear indiscriminadamente cambios de tarea, roleplay o Base64 legítimos. |
| `promption/resources/heuristics.yaml` | Sincronización byte a byte del YAML con `config/heuristics.yaml`. | Mantener reglas idénticas al desplegar el paquete. |
| `promption/filter/ensemble_filter.py` | El caso **educativo con cita** y señal inequívoca queda en `GUARDED` (no `ALLOWED`) aunque el ML rebase el umbral, y mantiene Output Guard. Registrar `quoted_educational_review` y umbral heurístico independiente en diagnóstico. | Reducir el FP del caso 58 sin conceder permisos ni saltar la protección posterior. |

**Archivos nuevos**:

| Ruta | Función |
|---|---|
| `tests/test_review_20261010.py` | 18 pruebas focalizadas con ML simulado para reglas y decisiones de tres estados. |
| `scripts/replay_known_benchmark.py` | Reproducción determinista de las decisiones con probabilidades históricas; avisa que no es evaluación independiente. |
| `data/processed/label_review_proposals_20261010.csv` | 17 propuestas por SHA-256 y `row_id`, con estatus `PENDING_HUMAN_REVIEW`. **No se aplican al entrenamiento ni se reetiqueta el test.** |
| `CAMBIOS_CODIGO.patch` | Diff unificado de los cinco archivos fuente cambiados, respecto del RAR recibido. |

## Resultados verificables

### Replay del benchmark conocido (1,000 filas: 500 etiqueta 1 y 500 etiqueta 0)

| Clasificación de bloqueo temprano | Original | Replay V4 |
|---|---:|---:|
| TP | 488 | 494 |
| FP | 5 | 4 |
| FN de bloqueo (a GUARDED) | 12 | 6 |
| TN de bloqueo | 495 | 496 |

En este replay `precision = 494/498 = 99.20%`, `recall = 494/500 = 98.80%`, `FPR = 4/500 = 0.80%`. Los seis casos etiqueta 1 no bloqueados quedan sujetos a la ruta `GUARDED` según el diseño, **no son filtraciones verificadas**. Se reutilizó la respuesta de ML previamente calculada, y las nuevas reglas se evaluaron con el texto; es una comparación *in-sample* sobre un benchmark que ya guio los cambios.

Los errores o etiquetas en conflicto afectan la validez de estas métricas. No se asegura que las mismas cifras se reproduzcan cuando se cambie de corpus, distribución real de solicitudes o modelo.

### Barrido heurístico del dataset corregido de 8,400 ejemplos (sin ML)

| Idioma | Etiqueta 0 bloqueada | Etiqueta 1 bloqueada |
|---|---:|---:|
| ES | 5 / 2,250 | 795 / 2,250 |
| EN | 0 / 1,950 | 425 / 1,950 |

Estas son métricas **solo heurísticas** sobre un dataset utilizado durante el desarrollo. No equivalen a la evaluación completa del ensemble.

### Pruebas técnicas

`18 passed` ejecutando `PYTHONPATH=. PROMPTION_ROOT=$PWD python -m pytest -q tests/test_review_20261010.py` y compilación sintáctica de los módulos Python. Los tests utilizan un ML simulado y no prueban inferencia del `.pkl` ausente, API remota, Output Guard real ni resistencia de extremo a extremo.

## Cambios propuestos que NO se aplicaron deliberadamente

- **No se aplicaron cuatro reetiquetados automáticos**: 102 (Zenny) necesita jerarquía/contexto, 321 es ficción ambigua, 791 merece revisión de bypass y 939 se parece a spam/marketing más que a prompt injection. Es impropio declararlos todos ataques probados o mejorar las métricas relabelando el test que se observó.
- **No se bloquea automáticamente** `forget about everything`: puede ser un cambio legítimo de la tarea del usuario; regla de severidad media.
- **No se bloquea automáticamente** `evil AI` o `IA malvada`: un prompt dañino no es, por esa sola característica, un ataque a la jerarquía de instrucciones; regla de severidad media.
- **No se bloquea cualquier mención a DAN**, solo un mandato de respuesta dual y comportamiento deliberadamente opuesto. El fragmento incompleto 989 queda sin bloqueo heurístico alto.
- **No se elevó a alta la regla general** `secret_obfuscation_en`; la regla nueva de alta severidad es explícita en el intento de ocultamiento para evitar falsos positivos de Base64 legítimo.
- **No se cambiaron** Output Guard, herramientas, autorización ni el LLM en esta versión: los cambios solicitados y verificables se concentran en filtro, umbral y anotaciones.

## Antes de usar en producción

1. Guardar copia del proyecto actual y aplicar el ZIP de parche en una rama separada. Los CSV históricos, modelos, medios y credenciales reales siguen en el proyecto local original.
2. Ejecutar `python -m pytest -q tests/test_review_20261010.py` y las pruebas preexistentes del proyecto (no incluidas en el RAR).
3. Confirmar qué archivos YAML está cargando la aplicación: configuración editable y copia empaquetada deben coincidir en reglas y umbrales.
4. Medir el umbral `0.60` en **validación nueva** y luego usar test externo nunca visto. Si eleva FPR en producción, revertir los tres umbrales a `0.66` antes de promover la versión.
5. Revisar las 17 propuestas con dos anotadores; si se adjudican, crear nueva versión de corpus y reservar un test nuevo, no sobrescribir la verdad de referencia de este benchmark.
6. Repetir el ensayo con el modelo real, `BLOCKED/GUARDED/ALLOWED`, permisos, Output Guard y secretos sintéticos; medir errores del proveedor, latencia y finalización de solicitudes legítimas.

**Limitación principal:** el `.pkl` activo y los tests originales no estaban en este RAR. Se pudo probar la lógica y hacer replay histórico, pero no ejecutar inferencia real del modelo ni demostrar disminución de vulneraciones reales.
