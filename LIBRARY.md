# Promption como librería

Promption tiene dos paquetes: `promption` para Python y `@promption/ai-sdk` para
JavaScript/TypeScript. La Filter API, el dashboard y los scripts consumen el paquete
Python. El Chat Service usa su pipeline, motor de permisos y ejecución MCP; Next.js
consume el middleware de AI SDK. Los productos y reglas de la tienda permanecen en
la app, mientras que los mecanismos de protección están en la librería.

## Integración con Vercel AI SDK

Desde `demo/`, la dependencia está instalada con
`"@promption/ai-sdk": "file:../packages/ai-sdk"`. Para otra app local:

```bash
npm install /ruta/a/Promption/packages/ai-sdk ai @ai-sdk/openai
```

Todo este código se ejecuta en el servidor:

```ts
import { createPromption } from '@promption/ai-sdk';
import { openai } from '@ai-sdk/openai';
import { generateText, streamText, wrapLanguageModel } from 'ai';

const promption = createPromption({
  baseUrl: process.env.FILTER_API_URL!,
  apiKey: process.env.PROMPTION_API_KEY!,
});

const identity = { userId: session.user.id, roles: session.user.roles, authenticated: true };
const model = wrapLanguageModel({
  model: openai(process.env.OPENAI_MODEL!),
  middleware: promption.middleware({ identity }),
});

const result = await generateText({ model, system: 'Tu instrucción de aplicación', prompt: text });
// El mismo model se usa con streamText({ model, system, prompt: text }).
```

`session` y `text` los resuelve tu aplicación. Los roles y la autenticación deben
proceder de una sesión validada por el servidor. Nunca aceptes roles que envíe el
navegador ni expongas la API key con variables `NEXT_PUBLIC_*`.

El middleware valida la entrada, revisa resultados de herramientas como datos no
confiables y valida texto y argumentos de herramientas generados por el modelo.
Bloquea ante errores del servicio de seguridad. En `streamText`, retiene los eventos
hasta comprobar el resultado completo; el cliente recibe solamente la salida
validada. Puedes mostrar un indicador de procesamiento mientras tanto y usar
`AbortSignal` para cancelar. El buffer tiene un límite configurable, por defecto
1 MiB. Los archivos binarios del modelo se rechazan: genera los archivos mediante
las herramientas MCP, validando su contenido antes de crearlos.

### Permisos de herramientas

```ts
const middleware = promption.middleware({
  identity,
  toolPolicies: {
    catalog: { roles: ['customer', 'ventas', 'admin'] },
    web_search: { roles: ['ventas', 'admin'] },
    payroll: { roles: ['admin'] },
  },
});
```

Cuando proporcionas `toolPolicies`, una herramienta ausente del mapa se deniega.
Sin sesión no hay llamadas a herramientas. Un usuario autenticado sin ese mapa
puede utilizar las herramientas que tú entregues al modelo; conserva también la
ACL en el servidor que ejecuta la operación. Para herramientas de AI SDK o de un
cliente MCP con `execute`, usa `promption.protectTool(tool, { name, identity, policy })`
para comprobar permiso, argumentos y resultado alrededor de su ejecución.
Las confirmaciones de operaciones sensibles se implementan con `needsApproval`
del tool de AI SDK o con la interfaz de tu app.

### Backend y políticas personalizados

La librería no obliga a pasar por el Chat Service. El transporte predeterminado
llama directamente a `/api/v1/filter` y `/api/v1/output-guard` de Filter API. La
app de este repositorio usa `createGuardEndpointTransport({ url, token })` para
conservar sus políticas de negocio y controles del panel admin en `/api/v1/ai/guard`.
También puedes suministrar `transport: async request => ({ allowed, text, action })`.

`originalText` permite indicar la solicitud original durante un flujo con varias
herramientas. Si se omite, se valida el último mensaje del usuario. Los resultados
de herramientas se validan aparte; las instrucciones confiables van en `system`.
`PromptionError` expone `code`, `status` y `direction`, sin incluir el texto protegido.
`onDecision` recibe decisiones y metadatos, sin prompts ni secretos.

### Detección conversacional

La revisión acumulativa está activada en el middleware: antes de `generateText` o
`streamText` envía al filtro mensajes del usuario, respuestas del asistente como
contexto y resultados de herramientas con su origen separado. El filtro inspecciona
mensajes individuales, secuencias reconstruidas, texto de resultados JSON y aliases
sencillos definidos en turnos anteriores. Combina las comprobaciones con OR y aplica
el ensemble existente a la secuencia. Las reglas adicionales están en
`conversation_rules` de `heuristics.yaml`.

La app conserva evidencia de seguridad separada del historial visible. Recortar
el contexto del modelo no elimina esa evidencia; está aislada por tenant, usuario,
roles, sesión y conversación. También se revisa cada resultado MCP antes de volver
al modelo. El contexto recuperado se entrega como resultado de herramienta, sin
convertir datos externos en instrucciones `system`.

En otra app, el middleware revisa todo el transcript que recibe. Si tu aplicación
recorta el transcript, proporciona su evidencia conservada por el servidor mediante
`securityMessages`. No compartas ese estado entre usuarios. Las tools protegidas
revisan también el contexto de `execute` antes de ejecutar la operación.

```ts
middleware: promption.middleware({ identity, securityMessages })
```

Los límites por defecto son 128 mensajes y 100000 caracteres, configurables mediante
`conversation_guard` en Python y `maxConversationMessages` / `maxConversationChars`
en el SDK. Al superar el límite se bloquea; la app pide iniciar otra conversación.
No se descartan fragmentos antiguos silenciosamente. El transporte exige que Filter
API confirme haber revisado el contexto. Un transporte personalizado debe evaluar
`request.messages` además de `request.text`.

Esta capa detecta los patrones y reconstrucciones cubiertos por sus reglas y el
modelo disponible; no garantiza detectar cualquier estrategia semántica nueva. La
ACL y Output Guard se mantienen como controles independientes.

## Paquete Python

```bash
pip install -e '.[api,mcp]'
```

Uso directo, sin FastAPI ni OpenAI:

```python
from promption import Promption, Identity

protection = Promption()
identity = Identity('user-123', ('customer',), authenticated=True)
input_decision = protection.check_input('Consulta el catálogo', identity)
if input_decision.allowed:
    output_decision = protection.check_output(model_response, identity)
    if output_decision.allowed:
        deliver(output_decision.text)
```

Incluye reglas heurísticas predeterminadas. El modelo ML se carga de forma lazy
cuando existe el artefacto entrenado; si no existe, se conserva el comportamiento
heurístico y se puede exigir Output Guard. No se incluyen modelos entrenados,
claves ni datos de clientes en el wheel.

Configura rutas antes de importar los componentes mediante `PROMPTION_ROOT`,
`PROMPTION_CONFIG_FILE` y `PROMPTION_HEURISTICS_FILE`. La app usa su `config/`;
una instalación fuera del repositorio usa los YAML incluidos en el paquete. Los
archivos de datos y modelos se resuelven contra la raíz de tu app. No se escribe
en `site-packages`, y los valores por defecto no crean archivos de logs.

| Componente | Import público |
| --- | --- |
| Heurística, ML y ensemble | `promption.filter` |
| Detección y redacción de salida | `promption.output_guard` |
| Detección acumulativa | `promption.ConversationGuard`, `ConversationMessage` |
| Pipeline local y async | `promption.Promption`, `promption.AsyncGuardPipeline` |
| ACL de recursos configurable | `promption.policies.PolicyEngine`, `ResourcePolicy` |
| Registro MCP y ACL por herramienta | `promption.tools.mcp.MCPToolExecutor`, `ToolPolicy` |
| DOCX, PDF, XLSX, CSV, TXT y lectura web limitada | `promption.tools.runtime` |
| API, autenticación de tenant y autorización | `promption.api` |
| Cliente async de Filter API | `promption.client.FilterClient` (extra `http`) |
| Historial aislado por identidad y tenant | `promption.conversation.ConversationStore` |
| Estado y cambios de controles de seguridad | `promption.state.SecurityStateStore` |
| Auditoría estructurada | `promption.utils.structured_logger` |
| Entrenamiento y benchmarks | `promption.training`, `promption.benchmark` |
| Extracción PDF y transcripción | `promption.utils.pdf_extractor`, `audio_transcriber` |
| Adaptadores de modelos para benchmark | `promption.llm` |

Las dependencias pesadas son opcionales: `api`, `mcp`, `embeddings`, `media`,
`reports`, `http`. `AsyncGuardPipeline` compone funciones async de filtrado y salida con
un `PolicyEngine`; tu framework adapta la decisión a HTTP. Configura ese motor con
reglas y asignaciones de roles de tu negocio. El executor MCP recibe tus handlers y
sus `ToolPolicy`, y usa el SDK oficial MCP para esquemas, registro y ejecución.

## Construcción, distribución y comprobación

```bash
uv build
cd packages/ai-sdk && npm pack
```

El wheel en `dist/` y el tarball de npm se instalan en otros proyectos con
`pip install /ruta/promption-1.1.0-py3-none-any.whl` y `npm install /ruta/promption-ai-sdk-1.1.0.tgz`.
Estos comandos construyen paquetes locales; no publican en PyPI ni npm.

```bash
python -m pytest tests/ -q
node --test packages/ai-sdk/test/*.test.js
cd demo && npm run build
```

Los imports antiguos de `src.*` siguen disponibles como aliases de compatibilidad.
Las nuevas integraciones deben usar `promption.*` y `@promption/ai-sdk`.
