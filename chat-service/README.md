# Chat Service - Backend Demo

Servicio de chat específico para la demo de Promption Shop. Aplica las políticas y ejecuta herramientas MCP; las llamadas a OpenAI pasan por Vercel AI SDK en Next.js.

## 🏗️ Arquitectura

```
Navegador → Next.js /api/chat → Chat Service (políticas y MCP)
                                  ↘ Next.js /api/ai/turn (Vercel AI SDK + middleware Promption) → OpenAI
```

## 📁 Estructura

```
chat-service/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app entry point
│   ├── routes.py         # API endpoints
│   ├── models.py         # Pydantic models
│   ├── llm_client.py     # Puente al Vercel AI SDK
│   ├── filter_client.py  # Filter API integration
│   ├── mcp_tools.py      # SDK MCP oficial + políticas por rol
│   ├── config.py         # Configuration
│   └── lib/
│       ├── __init__.py
│       └── shop.py       # Utilidades de tienda (system prompts, secret markers)
├── requirements.txt
├── Dockerfile
└── .env.example
```

## 🚀 Endpoints

- `POST /api/v1/chat` - Procesar mensaje del chat
- `POST /api/v1/chat/stream` - Estados y resultado por SSE
- `POST /api/v1/chat/cancel` - Detener una ejecución activa
- `POST /api/v1/ai/guard` - Entrada/salida de Promption para el middleware del modelo
- `GET /api/v1/health` - Health check
- `GET /api/v1/status` - Estado del servicio
- `POST /api/v1/tools/execute` - Deshabilitado (403); las tools se invocan desde `/chat` con autorización por sesión
- `GET /api/v1/security/state` - Estado efectivo del filtro y Output Guard
- `POST /api/v1/security/state` - Actualizar controles desde el panel admin

## 🔗 Integraciones

- **Filter API**: `FILTER_API_URL` (en desarrollo local: `http://127.0.0.1:8000`)
- **LLM**: OpenAI mediante Vercel AI SDK en Next.js (`gpt-5.4-nano` por defecto; `gpt-5.4-mini` para archivos y continuación de herramientas)
- **MCP Tools**: SDK oficial `mcp==2.2.0` para registro, esquema y ejecución de herramientas de tienda y archivos DOCX/PDF/XLSX

## 🚀 Despliegue

### Local
```bash
cd chat-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

### Docker
```bash
docker build -t promption-chat-service .
docker run -p 8000:8000 promption-chat-service
```

### Render
1. Crear nuevo servicio web en Render
2. Conectar repositorio
3. Configurar variables de entorno (ver `.env.example`)
4. Deploy

## 🔧 Variables de Entorno

- `FILTER_API_URL`: URL obligatoria del Filter API; sin valor no se envían solicitudes al filtro
- `PROMPTION_API_KEY`: API key del negocio; el tenant se resuelve automáticamente
- `FILTER_API_KEY`: nombre anterior, aceptado temporalmente por compatibilidad
- `GEMINI_API_KEY`: API key de Google AI Studio / Gemini (opcional)
- `GEMINI_MODEL`: Modelo de Gemini (default: `gemini-3.1-flash`)
- `GROQ_API_KEY`: API key de Groq (opcional)
- `OPENROUTER_API_KEY`: API key de OpenRouter (opcional)
- `LLM_PROVIDER_ORDER`: Proveedores habilitados (default: `openai`)
- `LLM_PROVIDER_TIMEOUT_SECONDS`: Máximo por intento/proveedor (default: `8`)
- `LLM_TOTAL_TIMEOUT_SECONDS`: Presupuesto total de toda la cadena (default: `24`)
- `LLM_MAX_ATTEMPTS`: Intentos por modelo antes del siguiente fallback (default: `1`)
- `LLM_RETRY_BACKOFF_SECONDS`: Espera base entre reintentos opcionales (default: `0.35`)
- `OPENAI_MODEL`: modelo normal; debe coincidir con Next.js (`gpt-5.4-nano` en el ejemplo)
- `OPENAI_TOOL_MODEL`: modelo para archivos y herramientas; debe coincidir con Next.js (`gpt-5.4-mini` en el ejemplo)
- `VERCEL_AI_URL`: URL obligatoria del endpoint interno de Next.js `/api/ai/turn`
- `CHAT_SERVICE_TOKEN`: Secreto compartido con el backend de Vercel para impedir llamadas directas con roles falsificados
- `SECURITY_STATE_PATH`: Ruta opcional del estado operativo (por defecto `data/security-state.json`)
- `CORS_ORIGINS_STR`: Orígenes permitidos (comma-separated)

## 📝 Características

- ✅ Integración completa con Filter API existente
- ✅ Clasificación de entrada en `MALICIOUS`, `BENIGN` y `UNCERTAIN`
- ✅ OpenAI mediante Vercel AI SDK; proveedores alternativos solo si se habilitan explícitamente
- ✅ MCP tools con control de acceso por rol
- ✅ Policy Engine para clasificación de recursos y ACL previa al LLM
- ✅ Recuperación de datos únicamente después de autorizar su tier
- ✅ Sesión firmada en el frontend y autenticación servidor-a-servidor opcional
- ✅ System prompts dinámicos según rol de usuario
- ✅ Detección de fugas de información confidencial
- ✅ Output Guard para respuestas del LLM
- ✅ Health checks y monitoreo

## Tool calls del bot

Las tools de datos de la tienda usan [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
versión 2.2.0. `MCPServer` registra funciones de negocio, genera los esquemas y valida
sus argumentos. Se crea un catálogo MCP independiente para cliente, ventas y administrador;
el visitante no recibe tools y la tool de secretos restringidos no se registra. El chat
vuelve a comprobar sesión y roles antes de llamar a `MCPServer.call_tool`.

La conexión es interna al proceso: no se publica `/mcp`, porque la autenticación de la demo
entra por el proxy firmado de Next.js. Las funciones que devuelven los datos de prueba,
la política de acceso y el Output Guard siguen siendo lógica propia del proyecto.
Las tools de internet, diálogos y archivos conservan sus validaciones de dominio.

El modelo puede solicitar herramientas durante `POST /api/v1/chat`. El servidor ofrece únicamente
las herramientas permitidas por la sesión validada en Next.js y vuelve a comprobar permisos
antes de ejecutar cada llamada. El endpoint directo `/tools/execute` devuelve 403.

| Perfil | Consultas de tienda | Internet | Diálogos | Archivos en chat |
|---|---|---|---|---|
| Visitante sin sesión | No usa tools | No | No | No |
| Cliente | Datos públicos | No | Sí | DOCX, PDF, XLSX, TXT, CSV y documentos Markdown autorizados |
| Ventas | Datos públicos e internos | Sí | Sí | DOCX, PDF, XLSX, TXT, CSV y documentos Markdown autorizados |
| Administrador | Datos públicos, internos y confidenciales | Sí | Sí | DOCX, PDF, XLSX, TXT, CSV y documentos Markdown autorizados |

La descarga de un documento confidencial pide confirmación en la interfaz. La herramienta
no envía correos ni modifica datos de negocio. Las consultas web se limitan a HTTPS público;
no acceden a IP privadas, no comparten datos internos y solo abren URLs indicadas por el
usuario o devueltas por una búsqueda. Las páginas se tratan como datos no confiables, se
analizan con el filtro y no pueden activar herramientas de negocio posteriores. Internet se
suspende si el filtro de entrada o Output Guard está desactivado. El Output
Guard y la política de salida se aplican al texto final y a los documentos.

Para OpenAI, configure `OPENAI_API_KEY` solo en el servidor Next.js y el mismo
`CHAT_SERVICE_TOKEN` en Next.js y Chat Service. Chat Service usa `VERCEL_AI_URL`
para enviar las llamadas del modelo a `/api/ai/turn`, que utiliza Vercel AI SDK y
el proveedor oficial de OpenAI. El middleware `wrapLanguageModel` consulta a
Promption antes y después de cada generación. La política y Output Guard también
se aplican en el flujo de chat. `gpt-5.4-nano` atiende los turnos normales;
`gpt-5.4-mini` atiende la creación de archivos y las continuaciones con herramientas.

### Historial de conversación

El proxy de Next.js asigna una cookie `chat_session` HttpOnly a cada conversación. El servicio guarda hasta 12 pares de mensajes durante 8 horas y envía al modelo los turnos recientes dentro de un límite de 12 000 caracteres. El historial se vincula al identificador de usuario, sus roles y su estado de autenticación; al iniciar o cerrar sesión se renueva la conversación. La interfaz recupera los turnos al volver a abrir el chat y ofrece **Nueva conversación** para comenzar sin contexto anterior. Los mensajes bloqueados y las respuestas que detectan filtración no se añaden al historial. Las páginas web no están disponibles en una conversación que contenga datos internos o confidenciales.

El almacenamiento actual está en memoria del proceso: reiniciar Chat Service borra las conversaciones y varias réplicas necesitarían un almacén compartido.

### Progreso y adjuntos

`POST /api/v1/chat/stream` transmite eventos SSE `status` y un evento final `result`. Next.js los reenvía desde el mismo origen mediante `POST /api/chat` con `Accept: text/event-stream`, manteniendo el token del servicio en el servidor. Ambos chats muestran la etapa actual: revisión, consulta de herramientas, generación de archivo y validación de salida. El endpoint JSON sigue disponible. Mientras una conversación procesa una petición, el servidor rechaza otro turno con HTTP 409. `POST /api/v1/chat/cancel` permite detener la tarea activa.

Cuando el usuario solicita un archivo, el servicio exige `make_document` si el modelo no lo llamó por sí solo. La herramienta corre mediante el SDK MCP en el servidor y admite DOCX, PDF, XLSX, TXT y CSV. La interfaz muestra un botón de descarga únicamente si la respuesta contiene una acción `attachment` o un documento existente autorizado. Si no se pudo crear el adjunto, la respuesta lo indica explícitamente.
