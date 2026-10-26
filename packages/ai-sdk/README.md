# @promption/ai-sdk

Middleware de Promption para Vercel AI SDK 6. Incluye validación de entrada y
salida, streaming validado antes de entregar contenido, protección de herramientas,
comprobación de resultados no confiables y errores sin exponer texto protegido.

Desde **1.5.0**, configura `protection: 'balanced'` (predeterminado),
`'conversational'` o `'strict'` en `createPromption`. Para ajustar los controles
independientemente: `protection: { profile: 'balanced', inputUncertainty: 'review',
scopeAmbiguity: 'clarify' }`. `inputUncertainty` admite `review | block` y
`scopeAmbiguity`, `clarify | block`. Los perfiles no pueden anular vetos,
permisos o revisión de salida. Las aclaraciones son fijas,
sin generación ni tools. No configures perfiles con datos del navegador.
`onDecision` incluye `control` y `protection`; los errores distinguen también
autorización de herramientas. Ver [guía de perfiles](../../docs/protection_profiles_20261025.md).

En **1.7.0**, las señales ML inciertas pueden recibir un veto adicional de política:
`reviewBlockThreshold` vale `0.85`, `0.75` y `0.66` en conversacional, equilibrado
y estricto. No cambia los pesos del clasificador ni relaja vetos existentes.
El motivo `risk_policy_veto` conserva la inyección como incierta. Son scores de
detección, no probabilidades calibradas. Estos ajustes pertenecen al servidor.

Registra los valores confidenciales con `createPromption({ protectedValues: [secret], ... })`.
La revisión local cubre representaciones conocidas, codificaciones habituales y
fragmentos de ocho caracteres para tokens opacos largos. También comprueba los
argumentos de `protectTool` antes de ejecutar efectos. No cubre cualquier cifrado
ni garantiza detectar fragmentos más pequeños repartidos entre turnos. Nunca
envíes `protectedValues` al navegador ni los cargues desde mensajes de usuario.

Para proveedores que rechazan uniones JSON Schema en salidas estructuradas, usa
`createContextEvaluator({ model, schemaMode: 'portable' })`. Se mantienen las
validaciones de coherencia, origen y evidencia en tiempo de ejecución. El modo
predeterminado sigue siendo `constrained`. Ver [evaluación 1.7](../../docs/precision_improvement_20261025.md).

Desde **1.7.1**, ese esquema portable combina ataque y origen en un enum para
impedir contradicciones como «sin ataque / origen usuario». La intención pública
conserva sus campos canónicos separados y sus validaciones en tiempo de ejecución.

En **1.6.0**, `onDecision.assessments` separa inyección, alcance y autorización;
cada control conserva su motivo y evaluaciones, incluso ante errores. Los tres
perfiles revisan la incertidumbre de entrada por defecto; `strict` bloquea la
ambigüedad de alcance. `inputUncertainty: 'block'` conserva el veto de toda
incertidumbre como opción explícita del servidor. Las citas analíticas se conservan
íntegras para el evaluador y el modelo. Si el backend informa
`requires_scope_review: true`, se exige `scopeEvaluator`; sin él se devuelve
`SCOPE_REVIEW_REQUIRED` antes de generar. Las tools conservan su procedencia no
confiable y las aclaraciones por información faltante no ejecutan el generador.
Consulta [contrato y medición local](../../docs/context_intent_review_20261025.md).

```ts
import { createPromption } from '@promption/ai-sdk';
import { wrapLanguageModel, generateText } from 'ai';
import { openai } from '@ai-sdk/openai';

const promption = createPromption({
  baseUrl: process.env.FILTER_API_URL!,
  apiKey: process.env.PROMPTION_API_KEY!,
});
const model = wrapLanguageModel({
  model: openai(process.env.OPENAI_MODEL!),
  middleware: promption.middleware({
    identity: { userId: session.user.id, roles: session.user.roles, authenticated: true },
    toolPolicies: { catalog: { roles: ['customer', 'ventas', 'admin'] } },
  }),
});
const result = await generateText({ model, system: 'Instrucciones de tu app', prompt: text });
```

`session` y `text` pertenecen a tu aplicación. La misma configuración funciona
con `streamText`; el middleware retiene la salida hasta que se aprueba completa.
Usa siempre credenciales y roles resueltos en el servidor. `protectTool` envuelve
el método `execute` de tools de AI SDK o MCP. Los usuarios sin sesión no ejecutan
herramientas y una herramienta no incluida en `toolPolicies` se deniega.
Si se omite `toolPolicies`, se deniegan todas las herramientas. `protectTool`
también requiere `policy`: usa `{}` para permitir a usuarios autenticados o
`{ roles: ['admin'] }` para restringirla por rol.

Puedes usar `createGuardEndpointTransport({ url, token })` con un backend que
responda `{ allowed: boolean, text: string, action?: string }`, o pasar un
`transport` personalizado a `createPromption`. El transporte predeterminado usa
Filter API de Promption, con `tenantId` opcional para comprobar el tenant.

`PromptionError` ofrece `code`, `status` y `direction`. Un fallo de red o una
respuesta inválida bloquean la operación. `maxTextChars` (100000) y
`maxStreamBytes` (1048576) limitan contenido y memoria. El middleware no expone
razonamiento ni cuerpos crudos del proveedor por defecto. Los archivos binarios
producidos directamente por el modelo se rechazan; usa el MCP del servidor para
crear archivos a partir de contenido previamente validado.

La guía completa y la implementación Python están en `LIBRARY.md` del repositorio.
La revisión acumulativa envía el transcript con el origen de cada mensaje a Filter
API antes de cada llamada. Detecta secuencias fragmentadas, aliases sencillos y
combinaciones de resultados de tools. Si recortas el historial, entrega la evidencia
conservada por tu servidor en `securityMessages`; conserva su aislamiento por sesión.
Los límites por defecto son 128 mensajes y 100000 caracteres. Se bloquea al superar
los límites o si el backend no confirma la revisión. Los transportes personalizados
deben evaluar `request.messages`; la detección no garantiza cubrir toda estrategia
semántica nueva.
El paquete se distribuye localmente con `npm pack`; no está publicado en un registry.

## Alcance del sistema

A partir de 1.3.0 puedes usar `scopeEvaluator: createContextEvaluator({ model })` para
obtener intención canónica, procedencia y alcance en una sola evaluación estructurada.
Se importa de `@promption/ai-sdk`. El historial, política e identidad se resuelven en
el servidor; el evaluador no reemplaza ACL ni Output Guard. Ver
[contrato y límites](../../docs/context_intent_20261023.md).

La integración anterior sigue disponible:
`scopeEvaluator: createScopeEvaluator({ model: openai(process.env.OPENAI_MODEL) })`
a `createPromption` para evaluar el alcance definido en `generateText({ system, ... })`
o `streamText`. Importa `createScopeEvaluator` desde `@promption/ai-sdk`.
El middleware comprueba solicitudes y llamadas a herramientas con el historial.
`checkScope(text, { identity, systemPrompt, messages })` permite consultar la decisión:
`IN_SCOPE`, `OUT_OF_SCOPE` o `UNCERTAIN`, con `reason`, `allowed` y `status`.
Solo `IN_SCOPE` permite continuar. Los errores exponen la clasificación en `error.scope`.
El evaluador distingue las políticas comerciales de una petición de revelar instrucciones
del sistema. Identifica primero el tema y el permiso aplicable; esa evaluación interna
se descarta y solo se devuelve la clasificación con un código fijo de motivo.

Usa un modelo sin envolver para el clasificador, evitando recursión. Las instrucciones
deben proceder del servidor. Para `protectTool`, añade `systemPrompt` y contexto del
usuario. Una decisión de alcance no sustituye ACL, filtro de inyección ni Output Guard.
La evaluación semántica es probabilística y añade llamadas al modelo; el evaluador
predeterminado usa salida estructurada de AI SDK y un timeout de 30 segundos.

## Aclaraciones y aislamiento desde 1.4.0

El middleware solicita `isolate_history=true` al comprobar la conversación. Solo
si el backend devuelve `conversation.isolated_history=true` bajo el contrato
verificado, retira el historial anterior del contexto enviado al generador. La
evidencia original sigue disponible para auditoría. Se conserva el mensaje system,
el turno actual y los resultados posteriores de herramientas. Los alias, las
condiciones de activación, los seguimientos y el contenido de tools mantienen sus
controles. Una decisión independiente nunca autoriza una tool ni desactiva la
revisión de salida. Un backend anterior conserva el comportamiento conservador.

Un dictamen válido `UNCERTAIN/ambiguous` con intención inocua puede producir una
pregunta fija de aclaración. `checkScope().allowed` permanece `false`: no se llama
al generador ni se ejecutan herramientas, y la pregunta pasa por Output Guard.
Los dictámenes inválidos, errores, timeouts, ataques y herramientas propuestas no
usan ese camino. La salida estructurada JSON conserva el fallo cerrado.

Los eventos distinguen `REVIEW`, `CLARIFY` e `ISOLATE_HISTORY` de `BLOCK`. Una
aclaración no equivale a completar la tarea y debe contabilizarse aparte. El caché
del middleware está pensado para el turno y su bucle de tools: crea una instancia
de middleware por petición, con identidad, política y evidencia resueltas en el
servidor. Los permisos no proceden del historial ni de argumentos del usuario.
