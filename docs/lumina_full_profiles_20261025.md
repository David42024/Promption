# Evaluación local completa de Lúmina — Promption 1.7.1

## Universo y método

Se ejecutaron de nuevo los controles locales sobre **4.411 turnos** con historial de la competencia Lúmina: **13.233 ejecuciones** entre los tres perfiles. No hubo llamadas a proveedores ni gasto de API. Duración de la ejecución: 142.96 segundos. El modelo entrenado y las etiquetas no se modificaron.

La exportación contiene 5.262 turnos. Se excluyeron 31 anteriores al reinicio, 208 por motivos operativos y 612 sin etiqueta binaria utilizable. Los 4.954 del contador original son aportes completos equivalentes al pozo, no el número total de turnos.

Las referencias son etiquetas silver provisionales, sin adjudicación humana. La cohorte completa incluye exposición de entrenamiento y desarrollo. La partición por participante se informa aparte; también ha sido expuesta previamente a diagnósticos.

Los controles ejecutados son heurísticas, clasificador ML local, guard de conversación con aislamiento del historial cuando corresponde y política de riesgo del perfil. No se ejecutaron el evaluador semántico externo, el generador, herramientas ni el guard sobre respuestas nuevas. El historial disponible contiene mensajes de usuario y asistente; no reproduce todos los resultados históricos de herramientas.

## Todos los turnos elegibles: 2.233 positivos y 2.178 negativos

| Perfil | VP | FP | Sin veto local (FN*) | VN | FP / negativos | Ataques permitidos directamente |
|---|---:|---:|---:|---:|---:|---:|
| Conversacional | 667 | 103 | 1566 | 2075 | 4.73% | 0 |
| Equilibrado | 784 | 154 | 1449 | 2024 | 7.07% | 0 |
| Estricto | 1067 | 341 | 1166 | 1837 | 15.66% | 0 |

## Partición de prueba por participante: 389 positivos y 432 negativos

| Perfil | VP | FP | Sin veto local (FN*) | VN | FP / negativos | Ataques permitidos directamente |
|---|---:|---:|---:|---:|---:|---:|
| Conversacional | 196 | 9 | 193 | 423 | 2.08% | 0 |
| Equilibrado | 223 | 22 | 166 | 410 | 5.09% | 0 |
| Estricto | 273 | 38 | 116 | 394 | 8.80% | 0 |

## Sensibilidad: partición de prueba con anotación de confianza alta

| Perfil | VP | FP | Sin veto local (FN*) | VN | FP / negativos | Ataques permitidos directamente |
|---|---:|---:|---:|---:|---:|---:|
| Conversacional | 195 | 3 | 173 | 110 | 2.65% | 0 |
| Equilibrado | 221 | 4 | 147 | 109 | 3.54% | 0 |
| Estricto | 269 | 8 | 99 | 105 | 7.08% | 0 |

**FN\*** significa que no hubo veto en la entrada local; todos esos ataques quedaron en la ruta de revisión obligatoria. No equivale a una inyección exitosa, una respuesta autorizada ni una filtración. Tampoco demuestra que la revisión semántica posterior acertará.

## Interpretación

El perfil conversacional presenta menos rechazos locales de referencia negativa; el estricto bloquea más referencias positivas y también más negativas. El modo equilibrado registra 22 falsos positivos de 432 negativos en la partición de prueba (5,09%). La mayoría de los casos siguen necesitando evaluación adicional: estos resultados no describen el rendimiento final del sistema completo.

No es posible estimar exfiltración, ASR ni comparar sin protección frente a solo prompt usando esta ejecución local. Eso requiere generación y comprobación de salidas bajo las tres condiciones. La nueva comparación API de 120 casos / 360 episodios se ejecuta por separado, tras la autorización explícita para Groq y un máximo acumulado de US$7. Sus resultados no se incorporan a estas matrices locales.

## Reproducción y trazabilidad

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/research/evaluate_lumina_profiles.py --output /tmp/lumina-replay-nuevo
```

El directorio de salida debe ser nuevo. Las predicciones por turno permanecen en el directorio privado de resultados; el JSON público contiene únicamente agregados y hashes. Se verificaron la unicidad de las 13.233 filas, la monotonicidad de los bloqueos entre perfiles, las matrices recalculadas y la estabilidad de fuentes, código y modelo.

- [Agregados y hashes](../data/results/lumina_full_profiles_20261025.json)
- [Ejecutor reproducible](../scripts/research/evaluate_lumina_profiles.py)
