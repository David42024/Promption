# Muestra local: tres modos de Promption 1.6.0

**Resultado histórico.** La misma muestra se ejecutó con las políticas 1.7.0;
ver [cambios y comparación actual](precision_improvement_20261025.md). Esta tabla
conserva las mediciones de 1.6.0.

Fecha: 25/10/2026. **240 casos × 3 perfiles = 720 ejecuciones nuevas** de la
heurística, ML entrenado, Conversation Guard y política de incertidumbre de entrada.
Coste de API: **US$0; cero llamadas**. Ejecución principal: 25.75 s.

## Muestra y trazabilidad

- Lúmina: 120 casos (60 positivos, 60 negativos), etiquetas semánticas previas/provisionales.
- Corpus públicos: 120 casos (60 positivos, 60 negativos), etiquetas de origen con correcciones y cuarentena existentes.
- Desglose de etiquetas `dataset` del corpus público: `{"Benigno": 60, "Custom": 25, "Jailbreak": 32, "OWASP": 1, "NEPI": 2}`.
- 107 casos tienen historial; Conversation Guard recibe el historial completo disponible y permite aislamiento solo si lo valida.
- Idioma público: 98 EN, 22 ES. Lúmina: 120 `es_or_mixed_unverified`; no se atribuye un idioma verificado a todos esos turnos.
- Se reutilizó íntegra la muestra estratificada y ya expuesta de 240 casos de la comparación anterior. No se seleccionaron casos por sus resultados actuales.
- SHA-256 de la muestra: `ac68860b773ad7b52c8a5f4b2d8a471344cf6c8b543008312b22b373c711cf3e`.
- SHA-256 de pesos ML: `81f0ae6c2d017617c449cd6e53c0a384613493056eb9034a4152b60c79de7bfa`; no se reentrenaron.

Código, configuración y resultados agregados:
[data/results/local_profiles_sample_20261025.json](../data/results/local_profiles_sample_20261025.json).
Las predicciones por ID, sin copiar el texto de participantes, quedan localmente en
`output/local_profiles_sample_160_20261025/final/predictions.json`, excluido de Git.
Los registros anteriores no se reemplazaron. El baseline 1.5.0 se volvió a ejecutar
sobre la misma muestra con los archivos centrales congelados de su estudio y su configuración original.

## Resultados del detector de entrada

Positivo significa ataque según la etiqueta disponible. **Predicción positiva = veto**;
no confundir esta matriz con rechazo final o éxito de ataque. Un FN de veto puede
seguir en revisión y no tiene permiso para generar.

| Perfil | TP veto | FP veto | FN sin veto | TN | FPR veto | Revisiones totales | Ataques en pase directo |
|---|---:|---:|---:|---:|---:|---:|---:|
| conversational | 69 | 6 | 51 | 114 | 5.0% | 163 | 0 |
| balanced | 69 | 6 | 51 | 114 | 5.0% | 163 | 0 |
| strict | 69 | 6 | 51 | 114 | 5.0% | 163 | 0 |

En cada modo: 69 de 120 ataques con veto (**57.5%**); los otros 51 (**42.5%**)
quedan en revisión. Los 120 ataques se reparten así entre veto y revisión, pero eso
**no equivale a 100% de defensa frente a un modelo real**. De los 120 negativos,
6 reciben veto, 112 revisión y 2 pase local. El FPR de veto es **5%**; el FNR de
veto es **42.5%**. El tratamiento operativo correcto de los pendientes exige
continuar con los guards configurados, no asumir que están aprobados.

De las 163 revisiones, 140 exigen además revisión semántica de contexto y todas
exigen Output Guard. Sin el evaluador cuando se exige contexto, el pipeline completo
falla cerrado con 503; eso no se cuenta como inyección confirmada ni tarea completada.

Los tres perfiles **coinciden en esta etapa local** porque todos usan la misma
heurística/ML y revisan señales débiles por defecto. Su diferencia actual es el
tratamiento posterior de ambigüedad semántica y de intención desconocida. No se
presenta uno como superior a partir de esta tabla.

### Por origen, mismo resultado en los tres modos

| Origen | Casos | TP veto | FP veto | FN sin veto | TN | FPR veto |
|---|---:|---:|---:|---:|---:|---:|
| lumina | 120 | 27 | 1 | 33 | 59 | 1.67% |
| public | 120 | 42 | 5 | 18 | 55 | 8.33% |

El desglose público por idioma es desigual: ES tiene solo 7 negativos (2 vetados)
y EN 53 negativos (3 vetados). No inferir superioridad por idioma con esas bases.

## Cambio respecto a 1.5.0, misma muestra y evaluación local

| Perfil | FP anterior → actual | Ataques con veto anterior → actual | Ataques en revisión anterior → actual |
|---|---:|---:|---:|
| conversational | 10 → 6 | 101 → 69 | 19 → 51 |
| balanced | 10 → 6 | 101 → 69 | 19 → 51 |
| strict | 118 → 6 | 120 → 69 | 0 → 51 |

Para conversacional y equilibrado, FPR de **8.33% a 5%** (4 vetos indebidos menos,
reducción relativa de 40%). La contrapartida son **32 ataques adicionales en
revisión**, con mayor dependencia y coste del evaluador contextual. Estricto deja
de vetar toda incertidumbre de entrada por defecto: antes vetaba 118/120 negativos.
Se mantiene el bloqueo de ambigüedad de alcance y la opción explícita del servidor
`input_uncertainty=block`. No se declara mejora global de seguridad sin completar
una nueva comparación con inferencia real.

## Reproducción separada de alcance histórico

Se reutilizó el **primer dictamen de alcance guardado** de 128 casos de la
comparación 1.4.0. En 112 casos no existe dictamen guardado; no se inventó uno.

| Perfil aplicado al dictamen guardado | Permitir | Aclarar | Bloquear |
|---|---:|---:|---:|
| conversational | 95 | 11 | 22 |
| balanced | 95 | 11 | 22 |
| strict | 95 | 0 | 33 |

Esta reproducción comprueba la política de perfiles, **no** evalúa de nuevo
intención, ni combina dictámenes viejos con decisiones nuevas para fingir una tasa
final. No mide la nueva calidad de aclaraciones `missing_information`, ausentes en
el formato antiguo. Las aclaraciones son preguntas fijas sin tools ni generación.

## Integración y límites

La integración HTTP local real FastAPI → transporte → AI SDK pasó en los tres
perfiles con **modelos simulados**: cita analítica conservada y revisada, salida
inspeccionada, contenido de tool bloqueado y cero ejecuciones sin permiso. La
revisión exigida sin evaluador se deniega. Esta comprobación no consume API.

Validación de implementación: 1196 pruebas Python aprobadas (10 omitidas),
140 pruebas nativas de AI SDK y tipos TypeScript sin errores. El benchmark
adicional de 661 registros terminó sin LLM ni reentrenamiento, en una carpeta
separada; sus valores proxy no son una medición nueva de exfiltración.

No hubo nueva generación con un LLM real, lectura de páginas externas, ejecución
de ataques sobre tools ni medición de exfiltración en esta muestra. Las etiquetas
son provisionales, y algunas positivas describen una inyección que aparecería en
un resultado de herramienta posterior: no necesariamente está en el mensaje de
entrada. La muestra ya fue usada durante desarrollo. Los números son evidencia de
regresión local, no un nuevo test independiente ni prueba de exfiltración casi cero.

La [calibración exploratoria ES/EN](context_intent_review_20261025.md) se informa
aparte; no se mezcla su 0% de FP con el 5% de esta muestra.

## Reproducir

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/research/evaluate_local_profiles.py \
  --output output/mi_repeticion_local
```

Requiere la muestra privada ya existente en
`output/corpus_repeat_140_20261024/cases_private.json`, su historial y los
artefactos del clasificador local. No lee `.env`, no crea clientes de OpenAI ni
consulta redes. La salida debe ser una carpeta nueva para no reemplazar resultados.
