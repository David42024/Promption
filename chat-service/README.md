# Chat Service - Backend Demo

Servicio de chat específico para la demo de Promption Shop. Maneja toda la lógica del chat, integración con LLM y MCP tools, usando el Filter API para seguridad.

## 🏗️ Arquitectura

```
Frontend (Vercel) → Chat Service (FastAPI) → Filter API (Security) → LLM
```

## 📁 Estructura

```
chat-service/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app entry point
│   ├── routes.py         # API endpoints
│   ├── models.py         # Pydantic models
│   ├── llm_client.py     # LLM integration (Gemini/Groq/OpenRouter)
│   ├── filter_client.py  # Filter API integration
│   ├── mcp_tools.py      # MCP tools de negocio
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
- `GET /api/v1/health` - Health check
- `GET /api/v1/status` - Estado del servicio
- `POST /api/v1/tools/execute` - Ejecutar MCP tools
- `GET /api/v1/security/state` - Estado efectivo del filtro y Output Guard
- `POST /api/v1/security/state` - Actualizar controles desde el panel admin

## 🔗 Integraciones

- **Filter API**: https://promption.onrender.com
- **LLM**: Gemini / Groq / OpenRouter
- **MCP Tools**: Tools específicos de la tienda

## 🚀 Despliegue

### Local
```bash
cd chat-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
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

- `FILTER_API_URL`: URL del Filter API
- `PROMPTION_API_KEY`: API key del negocio; el tenant se resuelve automáticamente
- `FILTER_API_KEY`: nombre anterior, aceptado temporalmente por compatibilidad
- `GEMINI_API_KEY`: API key de Google AI Studio / Gemini (opcional)
- `GEMINI_MODEL`: Modelo de Gemini (default: `gemini-3.1-flash`)
- `GROQ_API_KEY`: API key de Groq (opcional)
- `OPENROUTER_API_KEY`: API key de OpenRouter (opcional)
- `LLM_PROVIDER_ORDER`: Orden de fallback (default: `gemini,groq,openrouter`)
- `LLM_PROVIDER_TIMEOUT_SECONDS`: Máximo por intento/proveedor (default: `8`)
- `LLM_TOTAL_TIMEOUT_SECONDS`: Presupuesto total de toda la cadena (default: `24`)
- `LLM_MAX_ATTEMPTS`: Intentos por modelo antes del siguiente fallback (default: `1`)
- `LLM_RETRY_BACKOFF_SECONDS`: Espera base entre reintentos opcionales (default: `0.35`)
- `DEFAULT_MODEL`: Modelo LLM legado por defecto
- `CHAT_SERVICE_TOKEN`: Secreto compartido con el backend de Vercel para impedir llamadas directas con roles falsificados
- `SECURITY_STATE_PATH`: Ruta opcional del estado operativo (por defecto `data/security-state.json`)
- `CORS_ORIGINS_STR`: Orígenes permitidos (comma-separated)

## 📝 Características

- ✅ Integración completa con Filter API existente
- ✅ Clasificación de entrada en `MALICIOUS`, `BENIGN` y `UNCERTAIN`
- ✅ Fallback multi-proveedor ordenado: Gemini → Groq → OpenRouter, antes de modelos secundarios
- ✅ MCP tools con control de acceso por rol
- ✅ Policy Engine para clasificación de recursos y ACL previa al LLM
- ✅ Recuperación de datos únicamente después de autorizar su tier
- ✅ Sesión firmada en el frontend y autenticación servidor-a-servidor opcional
- ✅ System prompts dinámicos según rol de usuario
- ✅ Detección de fugas de información confidencial
- ✅ Output Guard para respuestas del LLM
- ✅ Health checks y monitoreo
