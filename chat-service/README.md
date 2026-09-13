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
│   ├── llm_client.py     # LLM integration (OpenAI/Gemini/Groq/OpenRouter)
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

## 🔗 Integraciones

- **Filter API**: https://promption.onrender.com
- **LLM**: OpenAI / Gemini / Groq / OpenRouter
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
- `FILTER_API_KEY`: API key del tenant
- `OPENAI_API_KEY`: API key de OpenAI Platform (opcional)
- `OPENAI_MODEL`: Modelo de OpenAI (default: `gpt-4o-mini`)
- `GEMINI_API_KEY`: API key de Google AI Studio / Gemini (opcional)
- `GEMINI_MODEL`: Modelo de Gemini (default: `gemini-3.1-flash`)
- `GROQ_API_KEY`: API key de Groq (opcional)
- `OPENROUTER_API_KEY`: API key de OpenRouter (opcional)
- `LLM_PROVIDER_ORDER`: Orden de fallback (default: `gemini,groq,openrouter`)
- `DEFAULT_MODEL`: Modelo LLM legado por defecto
- `CORS_ORIGINS`: Orígenes permitidos (comma-separated)

## 📝 Características

- ✅ Integración completa con Filter API existente
- ✅ Soporte multi-proveedor LLM (OpenAI/Gemini/Groq/OpenRouter)
- ✅ MCP tools con control de acceso por rol
- ✅ System prompts dinámicos según rol de usuario
- ✅ Detección de fugas de información confidencial
- ✅ Output Guard para respuestas del LLM
- ✅ Health checks y monitoreo
