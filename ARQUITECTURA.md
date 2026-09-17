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
- **Ubicación**: `/chat-service`
- **Propósito**: Backend específico para la demo de la tienda
- **Tecnologías**: FastAPI/Node.js + Integración con LLM
- **Componentes**:
  - Lógica del chat completo
  - Integración con LLM (Gemini/Groq/OpenRouter)
  - Policy Engine de recursos y tiers
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
  - Panel admin en dos módulos: operaciones/auditoría y estadísticas
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
    ↓ [Policy Engine: recurso + tier + ACL]
    ├─ DENY → respuesta determinista, no consume LLM
    ↓ [ALLOW: recuperación por MCP con segunda ACL]
LLM (Gemini → Groq → OpenRouter)
    ↓ [respuesta]
Backend Demo
    ↓ [para output-guard]
Backend Principal (Filter API)
    ↓ [veredicto: BLOCK/REDACT/PASS]
Backend Demo
    ↓ [respuesta final]
Frontend (Vercel)
```

Cada solicitud del Chat Service emite además un evento transaccional sanitizado
al Filter API. El evento contiene la decisión, clasificación, Policy Engine,
tools MCP, Output Guard, modelo y latencia, pero nunca el prompt ni la respuesta
completos. El panel admin usa esos eventos para auditoría y estadísticas.

Los interruptores del panel se guardan en el Chat Service y son consultados por
cada petición; el estado mostrado por React es el mismo que aplica el backend.

## Capas de decisión

1. **Ataque**: heurísticas + ML del Filter API, independiente del rol.
2. **Lectura**: Policy Engine clasifica el recurso y aplica ACL por tier.
3. **Recuperación**: la MCP tool vuelve a validar el rol antes de devolver datos.
4. **Salida**: Output Guard recibe los roles y bloquea o redacta contenido sensible.

La KB protegida no se introduce completa en el prompt. El LLM recibe únicamente el
contexto recuperado después de superar ambas comprobaciones ACL.

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
GEMINI_API_KEY=tu_key
GEMINI_MODEL=gemini-3.1-flash
GROQ_API_KEY=gsk_tu_key
OPENROUTER_API_KEY=sk-or-tu_key
LLM_PROVIDER_ORDER=gemini,groq,openrouter
CHAT_SERVICE_TOKEN=secreto_compartido_con_vercel
```

### Frontend Demo (Vercel)
```bash
NEXT_PUBLIC_CHAT_API_URL=https://backend-demo.onrender.com
CHAT_SERVICE_TOKEN=el_mismo_secreto_de_render
SESSION_SECRET=secreto_independiente_para_firmar_sesiones
NEXT_PUBLIC_PIF_ADMIN_SECRET=tu_secret_seguro
```

## ⚠️ Estado Actual

- ✅ Backend Principal: filtro de ataques y Output Guard
- ✅ Backend Demo: Policy Engine, recuperación MCP, ACL y fallback de LLM
- ✅ Frontend Demo: proxy servidor y presentación de decisiones
- ✅ Roles de sesión validados y firmados

## 🔧 Solución Inmediata (Temporal)

Mientras se implementa la arquitectura correcta:

1. **Mejorar configuración del filtro actual**
2. **Asegurar que el frontend use correctamente el Filter API**
3. **Documentar migración a arquitectura correcta**
