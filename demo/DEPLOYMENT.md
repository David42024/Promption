# Configuración de los tres servicios

Las URLs y los modelos son variables de entorno. Copia el ejemplo de cada
servicio y ajusta las direcciones según el entorno. No publiques las claves.

## Filter API (raíz del repositorio)

Usa [`.env.example`](../.env.example) como plantilla de `.env`:

```dotenv
PROMPTION_API_KEYS=mi-tenant:pk-clave-aleatoria
PROMPTION_ADMIN_API_KEYS=promption-platform:pk-admin-clave-aleatoria
PROMPTION_CORS_ORIGINS=https://tu-demo.vercel.app
FILTER_API_URL=https://tu-filter-api.com
FILTER_API_KEY=pk-clave-del-tenant
```

`FILTER_API_URL` y `FILTER_API_KEY` también permiten ejecutar
`scripts/test_filter_system.py`. El proceso de la API carga `.env` de la raíz.

## Chat Service

Usa [`chat-service/.env.example`](../chat-service/.env.example) como plantilla
de `chat-service/.env`. Para un despliegue, configura al menos:

```dotenv
FILTER_API_URL=https://tu-filter-api.com
PROMPTION_API_KEY=pk-clave-del-tenant
TENANT_ID=mi-tenant
VERCEL_AI_URL=https://tu-demo.vercel.app/api/ai/turn
OPENAI_MODEL=gpt-5.4-nano
OPENAI_TOOL_MODEL=gpt-5.4-mini
CHAT_SERVICE_TOKEN=secreto-compartido-largo
CORS_ORIGINS_STR=https://tu-demo.vercel.app
```

## Next.js en Vercel

Usa [`.env.example`](./.env.example) como plantilla de las variables de Vercel:

```dotenv
CHAT_API_URL=https://tu-chat-service.com
PIF_API_URL=https://tu-filter-api.com
SITE_URL=https://tu-demo.vercel.app
OPENAI_API_KEY=sk-tu-clave-openai
OPENAI_MODEL=gpt-5.4-nano
OPENAI_TOOL_MODEL=gpt-5.4-mini
CHAT_SERVICE_TOKEN=el-mismo-secreto-de-chat-service
SESSION_SECRET=otro-secreto-largo-e-independiente
PROMPTION_ADMIN_API_KEY=pk-admin-clave-aleatoria
```

Las llamadas a OpenAI salen de Next.js mediante Vercel AI SDK. Chat Service
mantiene la política y ejecuta las herramientas MCP. `CHAT_SERVICE_TOKEN` debe
coincidir en ambos servidores y los dos nombres de modelo también.

Para desarrollo local, usa las mismas variables con URLs
`http://127.0.0.1:8000`, `http://127.0.0.1:8001` y
`http://127.0.0.1:3000/api/ai/turn`, respectivamente.
