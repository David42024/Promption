# Promption 1.1.1: correcciones a partir de la competencia

## Qué cambió

- El filtro individual usa la misma normalización que el conversacional: Unicode
  NFKC, entidades HTML, marcas invisibles y espacios. Un salto de línea o un carácter
  invisible ya no separa artificialmente una instrucción de extracción.
- Se añadieron reglas específicas para solicitudes explícitas de instrucciones
  internas, claves protegidas, configuración activa y archivos de credenciales.
  Las menciones educativas de variables de entorno y archivos `.env` no bastan
  para activar esas reglas nuevas.
- La referencia a un «código interno de cada producto» deja de coincidir por sí
  sola con la regla de secreto interno. No autoriza a leer registros privados;
  siguen aplicándose ML, alcance, ACL y Output Guard.
- Se reconocen saludos informales, risas e identidad/límites públicos del asistente
  mediante coincidencia completa. Añadir una orden maliciosa invalida esa ruta.
- Una secuencia compuesta únicamente por mensajes benignos completos conserva
  esa ruta después de revisar las reconstrucciones. No se aplica a resultados de
  herramientas ni a mensajes desconocidos; no elimina ataques históricos.
- El límite `max_matches` limita la evidencia devuelta, no las reglas inspeccionadas.
  Antes, cinco coincidencias débiles podían impedir revisar una regla fuerte posterior.
- El middleware combina evidencia conservada y transcript actual sin omitir turnos
  intermedios. La combinación respeta el orden de ambas secuencias y la multiplicidad
  de mensajes repetidos; los límites siguen bloqueando sin recortar evidencia.
- Las matrices y ROC excluyen etiquetas desconocidas o no binarias. Se corrigió
  además la alineación de filas al usar probabilidades ML como alternativa para ROC.
- Las reglas del checkout y del wheel son idénticas. El wheel ahora hereda el umbral
  heurístico **0.8** del checkout, en lugar de su anterior **0.66**. Las señales medias
  pueden continuar a ML/generación vigilada; no equivalen a autorización. Esta diferencia
  de configuración debe conservarse al comparar versiones ya desplegadas.

Las respuestas generadas siguen requiriendo revisión de salida. Las comprobaciones
ejecutadas conservan su veto OR. La política de negocio y los permisos siguen siendo
responsabilidad de cada aplicación.

## Comparación diagnóstica local

Se congelaron las predicciones antes de modificar el código y se reprodujeron los
mismos **1238 mensajes individuales**: cohorte posterior al reinicio, etiquetas de
alta confianza, sin dependencia de contexto declarada y sin exclusiones operativas.
La comparación usa el mismo artefacto TF-IDF/LogisticRegression y el umbral 0.8
del checkout en ambas versiones. No se usaron llamadas a OpenAI.

| Resultado del filtro de entrada | Antes | Después |
|---|---:|---:|
| Verdaderos positivos | 224 | 231 |
| Verdaderos negativos | 466 | 469 |
| Falsos positivos | 22 | 19 |
| Falsos negativos | 526 | 519 |

Son etiquetas **silver provisionales**, no revisión humana independiente. Esta es
una evaluación diagnóstica usada para desarrollo; no es un nuevo conjunto de prueba
ciego. No reproduce el historial, el evaluador de alcance, las herramientas ni la
respuesta del modelo. Un FN aquí no demuestra que se revelara la clave. Los 519 FN
restantes indican que este filtro por sí solo sigue siendo insuficiente.
Un historial que todavía contiene instrucciones maliciosas sigue pudiendo bloquear
un saludo nuevo. La recuperación segura exige un nuevo contexto de conversación;
quitarlo únicamente del filtro mientras el modelo lo conserva abriría una evasión.

La regresión sobre los **661 casos del benchmark existente** pasó de 244 TP, 48 FP,
58 FN y 311 TN a 245 TP, 48 FP, 57 FN y 311 TN. No se modificó el modelo ni se ajustó
con ese conjunto. El modo `--no-llm` produce un proxy de detección, no una tasa
observada de extracción de secretos. Las mediciones de esta página no validan el
comportamiento completo de una aplicación desplegada.

Los resultados detallados y sus hashes quedan en el directorio privado
`output/research_20261023/`: `library_comparison.json`,
`library_baseline_predictions.json`, `library_baseline_source/` y
`library_existing_benchmark.json`. No contienen la clave real. Los chats y sus
correspondencias no deben publicarse sin revisión de privacidad.

Para repetir la comparación con las anotaciones locales:

```bash
python scripts/research/compare_library.py \
  --annotations output/research_20261023/etiquetas_provisionales.jsonl \
  --baseline output/research_20261023/library_baseline_predictions.json \
  --output output/research_20261023/library_comparison.json
```

## Verificación

- Python: **932 pruebas aprobadas, 10 omitidas**; incluye regresiones sintéticas de
  saludos, concatenaciones, Unicode, archivos, permisos, herramientas, historial,
  Output Guard y etiquetas indeterminadas.
- AI SDK: **68 pruebas aprobadas**, incluidos cinco casos nuevos de mezcla de evidencia.
- TypeScript: comprobación de tipos sin errores.
- Benchmark: `python scripts/run_benchmark.py --no-train --no-llm`, 661 filas.
- Dashboard: arranque por `AppTest` sin excepciones, además de su suite existente.
- API: arranque real de Uvicorn y `GET /api/v1/health` con HTTP 200.
- Wheel: construcción e instalación aislada; reglas empaquetadas y módulo de
  normalización verificados. El SDK también se empaquetó como tarball.

Los paquetes locales están en `output/releases/1.1.1/`. No se reentrenó con las
etiquetas automáticas, no se subieron chats ni credenciales y no se desplegó la app.
Para afirmar mejoras científicas se requiere revisión humana y una nueva evaluación
independiente con contexto completo, configuración y versiones fijadas.
