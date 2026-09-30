# @promption/ai-sdk

Middleware de Promption para Vercel AI SDK 6. Incluye validación de entrada y
salida, streaming validado antes de entregar contenido, protección de herramientas,
comprobación de resultados no confiables y errores sin exponer texto protegido.

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
