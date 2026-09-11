# Arquitectura del Sistema - Promption

## 🏗️ Arquitectura Correcta (3 componentes)

### 1. **Backend Principal - Filter API** (Proyecto Raíz)
- **Ubicación**: Directorio raíz de `Promption`
- **Propósito**: Sistema de detección de prompt injection replicable
- **Tecnologías**: FastAPI + Streamlit + Python
- **Componentes**:
  - `src/api/` - API REST de filtering
  - `src/filter/` - Lógica de detección (heurística + ML + ensemble)
  - `dashboard/` - Dashboard Streamlit
  - `config/` - Configuración reutilizable
- **Endpoints principales**:
  - `POST /api/v1/filter` - Filtrado de prompts
  - `POST /api/v1/output-guard` - Filtrado de respuestas
  - `GET /api/v1/health` - Health check
  - `GET /api/v1/logs/structured` - Logs estructurados
- **Despliegue**: Render (https://promption.onrender.com)

### 2. **Backend Demo - Chat Service** (Demo específico)
- **Ubicación**: Servicio separado (no implementado aún)
- **Propósito**: Backend específico para la demo de la tienda
- **Tecnologías**: FastAPI/Node.js + Integración con LLM
- **Componentes**:
  - Lógica del chat completo
  - Integración con LLM (Groq/OpenRouter)
  - MCP tools específicos de la tienda
  - Conexión con Backend Principal para filtering
- **Responsabilidades**:
  - Manejar toda la lógica del chat
  - Llamadas a los LLM
  - MCP tools de negocio
  - Integración con Filter API para seguridad
- **Despliegue**: Render (servicio separado)

### 3. **Frontend Demo** (Vercel)
- **Ubicación**: `/demo` (Next.js)
- **Propósito**: UI de la demo de la tienda
- **Tecnologías**: Next.js + React
- **Componentes**:
  - Tienda demo
  - Chat widget
  - Panel admin
- **Responsabilidades**:
  - Solo la UI del chat
  - Enviar prompts al Backend Demo
  - Recibir y mostrar respuestas
- **Despliegue**: Vercel (https://promptionsi.vercel.app)

## 🔗 Flujo de Datos Correcto

```
Usuario → Frontend (Vercel)
    ↓ [prompt]
Backend Demo (Render)
    ↓ [para filtering]
Backend Principal (Filter API)
    ↓ [veredicto: BLOCK/PASS]
Backend Demo
    ↓ [si PASS: llama a LLM]
LLM (Groq/OpenRouter)
    ↓ [respuesta]
Backend Demo
    ↓ [para output-guard]
Backend Principal (Filter API)
    ↓ [veredicto: BLOCK/REDACT/PASS]
Backend Demo
    ↓ [respuesta final]
Frontend (Vercel)
```

## ❌ Arquitectura Actual (Problemática)

### Problemas:
1. **Solo existe un backend** (Filter API) cuando deberían ser 2
2. **Frontend tiene lógica del chat** cuando debería estar en backend
3. **API keys en frontend** (inseguro)
4. **Lógica duplicada** entre frontend y backend

### Flujo actual (incorrecto):
```
Frontend (Vercel)
    ↓ [tiene lógica completa del chat]
LLM (Groq/OpenRouter) ← API keys en frontend
    ↓ [para filtering]
Backend Principal (Filter API)
    ↓ [solo filtering]
Frontend (Vercel)
```

## 🚀 Pasos para Corregir la Arquitectura

### Fase 1: Backend Demo (Chat Service) ✅ COMPLETADO
1. ✅ Crear servicio FastAPI separado en `chat-service/`
2. ✅ Implementar lógica completa del chat
3. ✅ Mover API keys de LLM al backend demo
4. ✅ Implementar MCP tools de negocio
5. ✅ Configurar integración con Filter API

### Fase 2: Frontend Simplificado
1. Simplificar `/demo/app/api/chat/route.js` para que solo reenvíe al backend demo
2. Eliminar API keys del frontend
3. Mantener solo UI y lógica de presentación

### Fase 3: Configuración de Despliegue
1. Desplegar Backend Demo en Render
2. Configurar variables de entorno correctas
3. Actualizar Vercel para conectar con Backend Demo

## 📝 Variables de Entorno por Servicio

### Backend Principal (Filter API)
```bash
PIF_API_URL=https://promption.onrender.com
PIF_TENANT_KEY=pif_demo_shop_123456
PIF_ADMIN_SECRET=tu_secret_seguro
```

### Backend Demo (Chat Service)
```bash
FILTER_API_URL=https://promption.onrender.com
FILTER_API_KEY=pif_demo_shop_123456
GROQ_API_KEY=gsk_tu_key
OPENROUTER_API_KEY=sk-or-tu_key
PIF_LLM_MODEL=llama-3.1-70b-versatile
```

### Frontend Demo (Vercel)
```bash
NEXT_PUBLIC_CHAT_API_URL=https://backend-demo.onrender.com
NEXT_PUBLIC_PIF_ADMIN_SECRET=tu_secret_seguro
```

## ⚠️ Estado Actual

- ✅ Backend Principal (Filter API): Funcionando en Render
- ❌ Backend Demo (Chat Service): NO existe
- ⚠️ Frontend Demo: Tiene lógica que debería estar en backend
- ⚠️ Filtro: Funciona pero puede que no esté configurado correctamente en el frontend

## 🔧 Solución Inmediata (Temporal)

Mientras se implementa la arquitectura correcta:

1. **Mejorar configuración del filtro actual**
2. **Asegurar que el frontend use correctamente el Filter API**
3. **Documentar migración a arquitectura correcta**
