# Corrección de rechazo por historial — Promption 1.3.3

## Causa y cambio

El caso de investigación `T01892` tenía como petición actual «Te amo». Esa petición
no era bloqueada por sí sola. El filtro ML de conversación clasificaba todo el
historial concatenado como malicioso; ya lo hacía incluso sin añadir el mensaje
actual. Se heredaba así un veto que no describía la intención de ese turno.

Se incorpora una transición para intervenciones completas e independientes,
definidas en la configuración del servidor con `independent_turn: true` dentro de
las reglas benignas: saludos, risas, reacciones sociales, agradecimientos y algunas
consultas completas de identidad, capacidades o política comercial.

La condición exige coincidencia de **todo** el mensaje actual, sin reglas maliciosas
en él. «Sí», «ok», «por favor», «hazlo», «continúa», «expórtalo» y otras referencias
no reciben esta propiedad. Añadir una instrucción a un saludo tampoco la conserva.

Antes de elegir la transición se revisan **todas las vistas heurísticas** del historial,
incluidos fragmentos reconstruidos, texto normalizado, compactación, alias y orígenes.
Cualquier veto de esas capas continúa bloqueando. La transición no se usa si hay
herramientas en el contexto, definiciones de alias o condiciones que activen un plan
en otro turno. La configuración proviene del servidor, no de un campo del cliente.

Cuando la petición es independiente y no hay vetos heurísticos, se evita ejecutar
el clasificador sobre la concatenación de temas anteriores. No se revoca un veto ML
ya ejecutado ni se cambia el ensemble OR. La transición con historial no benigno
marca `requires_output_guard=true`, `evaluation_mode=independent_turn` y
`reason=independent_turn_requires_output_guard`. Sin Output Guard activo, la fachada
rechaza la generación. ACL y evaluación de alcance siguen siendo obligatorias cuando
están configuradas. El middleware revisa la salida antes de entregarla.

El historial se conserva para la auditoría y el evaluador contextual. No se recorta
el contexto del modelo ni se descartan mensajes antiguos. Los ataques explícitos del
historial siguen bloqueando; esta corrección trata la contaminación del ML acumulado,
no permite ignorar cualquier advertencia histórica.

## API

`ConversationGuard.analyze(..., current_text=...)` permite aportar la petición actual
cuando no está incluida en `messages`. `/api/v1/filter` la proporciona desde `text`.
Así, el historial no puede confundirse con el turno actual y un fragmento nuevo se
combina con sus antecedentes aunque el cliente solo envíe turnos previos.

Se mantiene `message_count` igual al número de mensajes recibidos para compatibilidad
del protocolo; el texto actual se inspecciona además de ellos. La evidencia combinada
también está sujeta a los límites existentes. No se añadió un campo de autorización
que el usuario pueda establecer desde el chat.

## Reproducción local

Se comparó el código actual contra `promption-1.3.2-py3-none-any.whl`, conservando sus
reglas originales, el modelo base y el clasificador adicional a umbral 0.82. No hubo
reentrenamiento, ajuste de umbrales ni llamadas a OpenAI.

| Cohorte | Casos | FP antes → después | FN antes → después |
| --- | ---: | ---: | ---: |
| Conversaciones reales ampliadas | 420 | 16 → 14 | 19 → 19 |
| Submuestra real anterior | 40 | 2 → 1 | 1 → 1 |
| Controles sintéticos | 10 | 1 → 0 | 0 → 0 |

Los dos cambios de las 420 conversaciones fueron `T01892` y `T01782`, etiquetados
como legítimos. Ambos pasan con Output Guard requerido. Los 40 casos son un subconjunto
de los 420: no deben sumarse como observaciones independientes. Las etiquetas son
provisionales (silver); son diagnósticos exploratorios, no un nuevo test ciego ni
mediciones de filtración final de secretos.

Reutilizando las decisiones contextuales **ya guardadas** de los 37 casos reales
pareados, el conjunto de entrada pasa de 1 FP/1 FN a 0 FP/1 FN. Esto solo reproduce
la composición de capas; no vuelve a medir el LLM ni demuestra cómo respondería una
nueva llamada con el historial completo. La cohorte ampliada reconstruye los turnos
usuario/asistente disponibles; los ataques en herramientas se cubren además en pruebas
de regresión y controles sintéticos.

El benchmark de 661 casos, sin generación y sin entrenar, mantuvo TP245/FP48/FN57/TN311
en el perfil por defecto. Es un control de compatibilidad, no ASR medido con LLM.

## Pruebas y entrega

- 1056 pruebas Python aprobadas, 10 omitidas.
- 89 pruebas JavaScript aprobadas y tipos TypeScript comprobados.
- Regresiones de ataques fragmentados, alias, activadores, herramientas, contenido
  malicioso añadido a saludos, límites, ACL y Output Guard obligatorio.
- API temporal con Uvicorn: salud HTTP 200. Dashboard comprobado por AppTest en la suite.
- Paquetes locales Python y AI SDK 1.3.3; sin publicación ni despliegue.

Evidencia privada en `output/history_transitions_20261023/`: `summary.json`,
`predictions.json`, `cached_scope_replay.json`, `verification.json` y el código base
extraído del wheel para reproducir la comparación. Los archivos anteriores se conservan.

```bash
python scripts/research/replay_history_transitions.py \
  --research output/research_20261023 \
  --cases output/context_eval_comparison_20261023/cases_private.json \
  --wheel output/releases/1.3.2/promption-1.3.2-py3-none-any.whl \
  --adapted-model output/guardrail_experiments_20261023/adapted_classifier.pkl \
  --output /tmp/promption-history-replay-new
```
