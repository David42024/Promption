# Perfiles de protección — Promption 1.5.0

**Documento histórico de 1.5.0.** En 1.6.0, `strict` también revisa por defecto la
incertidumbre del detector. Sigue bloqueando la ambigüedad de alcance y permite
aclaraciones seguras por datos faltantes. Los nuevos umbrales, contratos y medición
están en [contexto y revisión](context_intent_review_20261025.md) y la
[comparación local de los tres perfiles](local_profiles_sample_20261025.md).
Las tablas siguientes describen 1.5.0 y no se atribuyen a 1.6.0.

En **1.7.0** los perfiles también aplican distintos umbrales de veto por riesgo
incierto, sin relajar vetos concluyentes. Los resultados actualizados y su coste
en falsos positivos están en [la evaluación 1.7.0](precision_improvement_20261025.md).

La [comparación posterior con 48 casos y 144 episodios nuevos](profiles_comparison_20261025.md)
encontró sobrebloqueo del modo estricto y no demostró superioridad entre los otros
dos perfiles. Sus resultados están separados de la reproducción parcial descrita abajo.

Los perfiles pertenecen al servidor de la aplicación. No se toman del texto del
usuario, del navegador, de documentos, del historial ni de argumentos de tools.
Se seleccionan al construir `Promption`, `AsyncGuardPipeline` o `createPromption`.

## Comportamiento

| Perfil | Incertidumbre del detector de entrada | Ambigüedad semántica compatible | Intención canónica desconocida |
|---|---|---|---|
| `conversational` | Revisión con Output Guard obligatorio | Aclaración fija | Puede pedir aclaración fija |
| `balanced` (predeterminado) | Revisión con Output Guard obligatorio | Aclaración fija | Bloquea |
| `strict` | Bloquea | Bloquea | Bloquea |

«Revisión» conserva el comportamiento `GUARDED`: exige revisar la salida y usa
el evaluador de contexto si está configurado. No instala por sí sola un modelo
semántico. Un perfil no sustituye los guards o las políticas que debe configurar
la aplicación.

Las dos decisiones son independientes. Por ejemplo, se puede elegir `balanced`
pero bloquear la incertidumbre de entrada y seguir ofreciendo aclaraciones de
alcance. No se cambiaron los umbrales heurísticos/ML, pesos, reglas ni artefactos
del clasificador. Los scores no se presentan como probabilidades calibradas.
`strict` es conservador: también puede bloquear conversaciones legítimas que
necesiten Output Guard por aislamiento de historial.

## Invariantes

- Cualquier veto definitivo del detector, del historial o de una capa ejecutada
  conserva su bloqueo. Se mantiene OR entre vetos.
- Las políticas de autorización y de alcance explícitamente prohibido se respetan
  en todos los perfiles. Un permiso procede del servidor, nunca de una afirmación
  del usuario o de una página.
- No se desactiva Output Guard, ni se permite entregar binarios sin inspección.
  En Python, la aplicación debe ejecutar `check_output` antes de entregar contenido.
- Las aclaraciones requieren un dictamen válido `UNCERTAIN/ambiguous`, una
  intención no sensible, origen de ataque `none` y ataque `none` o `unknown`.
  Una incertidumbre sin evidencia no se convierte en aprobación. La intención
  `unknown` solo puede aclararse en `conversational`.
- Los ataques identificados, extracción de secretos, escalada de privilegios y
  origen sospechoso conservan el bloqueo. `OUT_OF_SCOPE` no se reclasifica por perfil.
- No hay aclaración para una herramienta propuesta, salida JSON, timeout,
  respuesta inválida o fallo de un guard. La respuesta fija pasa por Output Guard;
  no llama al generador ni ejecuta tools. `allowed` sigue siendo `false`.

La revisión async comprueba el detector antes de decidir una aclaración semántica,
evitando que un dictamen ambiguo o favorable tape un veto de entrada. Se corrigió
también la conservación de fallos operativos con metadatos de intención de baja
confianza: no se convierten en `ambiguous`.

## Python

```python
from promption import Promption, ProtectionSettings

guard = Promption(
    protection=ProtectionSettings(
        profile="balanced",
        input_uncertainty="review",
        scope_ambiguity="clarify",
    ),
    scope_guard=application_scope_guard,
    policy=application_policy,
)
```

También admite `Promption(protection="strict")` y la misma opción en
`AsyncGuardPipeline`. Si se omite, Python lee `protection` mediante `load_config`;
la configuración distribuida y la del repositorio contienen:

```yaml
protection:
  profile: balanced
```

Las opciones `input_uncertainty` y `scope_ambiguity` son opcionales en YAML.
`PROMPTION_CONFIG_FILE` permite seleccionar el archivo de configuración de la
aplicación. Las configuraciones desconocidas se rechazan. Los ajustes resueltos
son inmutables y quedan en `decision.protection` / `decision.to_dict()`.

## Vercel AI SDK

```ts
import { createPromption, createContextEvaluator } from '@promption/ai-sdk';

const protection = createPromption({
  baseUrl: process.env.FILTER_API_URL!,
  apiKey: process.env.PROMPTION_API_KEY!,
  protection: {
    profile: 'balanced',
    inputUncertainty: 'review',
    scopeAmbiguity: 'clarify',
  },
  scopeEvaluator: createContextEvaluator({ model: classifierModel }),
  onDecision: event => audit(event),
});
```

`classifierModel` y `audit` los proporciona el servidor. Se conserva la
integración habitual `wrapLanguageModel({ model, middleware:
protection.middleware({ identity, toolPolicies }) })`. Cada petición usa identidad,
política y middleware propios. También admite `protection: 'strict'` y expone
`protection.protection` con los ajustes resueltos e inmutables.

No se admite cambiar el perfil en `middleware(...)`, `check(...)`, `checkScope(...)`
ni `protectTool(...)`. El tipo TypeScript lo impide y las propiedades adicionales
en JavaScript no alteran la configuración capturada al construir la instancia.
El perfil se configura en cada aplicación consumidora; `/filter` sigue siendo
un endpoint de detección, no un ejecutor de generación ni de perfiles de aplicación.
Los transportes personalizados deben informar `requiresOutputGuard: true` o
`action: 'GUARDED'` para su incertidumbre, además de comprobar historial y salida.

## Auditoría y evaluación

`GuardDecision.control`, `ScopeDecision.to_dict()` y los eventos del middleware
distinguen `injection`, `scope`, `authorization`, `output`, `input` y `operational`.
Las denegaciones de herramientas usan `authorization`. La incertidumbre de entrada
usa `uncertain_input`, sin fingir que hay una inyección confirmada. Los resultados
semánticos incluyen por separado `injection`: `detected`, `not_detected`,
`uncertain` o `not_evaluated`. No tener ataque detectado no prueba que la tarea
esté permitida; no tener intención estructurada tampoco prueba que sea inocua.

El perfil y las dos opciones efectivas se adjuntan a la auditoría. Para el artículo
se deben medir por separado: detección de inyección, cumplimiento de política,
permisos, aclaraciones, fallos operativos y tareas legítimas completadas. Una
etiqueta negativa de inyección no demuestra que la política permita esa tarea.

## Comprobación sobre evidencia existente, sin API

Se reprodujo **solo la decisión de aclaración** sobre los dictámenes guardados
de los 240 episodios protegidos de la evaluación 1.4.0. Trece episodios tenían
ambigüedad o aclaración fija. Resultado:

| Perfil | Aclaraciones posibles | Bloqueos conservados | Bloqueos que pasarían a aclaración |
|---|---:|---:|---:|
| conversational | 11 | 2 | 8 |
| balanced | 11 | 2 | 8 |
| strict | 0 | 13 | 0 |

Los ocho cambios afectan etiquetas negativas de origen/silver; tres aclaraciones
ya existían. No se generaron respuestas, no se completaron tareas, no se volvieron
a evaluar intenciones con un modelo ni se estimaron nuevos FPR/FNR o ASR. Los
perfiles no se compararon aún en una evaluación completa nueva. Esta reproducción
reutiliza casos expuestos durante desarrollo y no demuestra generalización.

```bash
.venv/bin/python scripts/research/replay_scope_profiles.py output/corpus_repeat_140_20261024
```

Los resultados anteriores de 720 episodios permanecen identificados como 1.4.0.
No se atribuyen a 1.5.0 ni se sustituyen por esta reproducción parcial.

## Verificación de implementación

- Python: **1159 aprobadas, 10 omitidas**.
- AI SDK: **124 aprobadas**, con modelos simulados y llamadas nativas a
  `generateText`/`streamText`; tipos TypeScript sin errores.
- Benchmark local sin LLM ni entrenamiento: **661 registros**; se conservaron
  el modelo y los resultados anteriores. El ASR proxy no es una medida nueva de
  exfiltración ni de eficacia de perfiles.
- API y dashboard: ambos respondieron HTTP 200 en su comprobación de salud local.
- Wheel verificado fuera del checkout, incluidos defaults empaquetados y perfil
  estricto; tarball de npm preparado para consumo local.
- Evidencia local de validación: `output/protection_profiles_20261025/`.
