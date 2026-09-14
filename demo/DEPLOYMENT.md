# Configuración de Variables de Entorno para Producción

## 🌐 URLs de Producción
- **Backend (Render)**: https://promption.onrender.com/
- **Frontend (Vercel)**: https://promptionsi.vercel.app/

## 🔧 Configuración en Render (Backend)

Las siguientes variables deben configurarse en el dashboard de Render:

### Variables de Entorno para Render
```
PIF_API_URL=https://promption.onrender.com
PROMPTION_API_KEYS=tenant123.unitru:pk-123-tenant123.unitru
PROMPTION_ADMIN_API_KEYS=promption-platform:pk-admin-clave-aleatoria
GROQ_API_KEY=gsk_TU_GROQ_KEY_REAL
OPENROUTER_API_KEY=sk-or-TU_OPENROUTER_KEY_REAL
GEMINI_API_KEY=TU_GEMINI_KEY_REAL
GEMINI_MODEL=gemini-3.1-flash
LLM_PROVIDER_ORDER=gemini,groq,openrouter
CHAT_SERVICE_TOKEN=GENERA_UN_SECRETO_COMPARTIDO_LARGO
```

### Pasos para configurar en Render:
1. Ve a tu dashboard de Render
2. Selecciona tu servicio web
3. Navega a "Environment" 
4. Añade cada variable de entorno con su valor correspondiente
5. Haz "Deploy" para aplicar los cambios

## 🚀 Configuración en Vercel (Frontend)

Las siguientes variables deben configurarse en el dashboard de Vercel:

### Variables de Entorno para Vercel
```
NEXT_PUBLIC_CHAT_API_URL=https://chat-service-l31i.onrender.com
PIF_API_URL=https://promption.onrender.com
PROMPTION_ADMIN_API_KEY=pk-admin-clave-aleatoria
CHAT_SERVICE_TOKEN=EL_MISMO_VALOR_CONFIGURADO_EN_RENDER
SESSION_SECRET=GENERA_OTRO_SECRETO_LARGO_E_INDEPENDIENTE
```

### Pasos para configurar en Vercel:
1. Ve a tu dashboard de Vercel
2. Selecciona tu proyecto
3. Navega a "Settings" → "Environment Variables"
4. Añade cada variable de entorno con su valor correspondiente
5. Haz "Redeploy" para aplicar los cambios

## ⚠️ IMPORTANTE: Seguridad

1. **CAMBIA los valores por defecto**:
   - `PROMPTION_ADMIN_API_KEY` debe ser un string aleatorio largo
   - cada key en `PROMPTION_API_KEYS` debe ser única por tenant

2. **Nunca commits secrets reales** en el repositorio

3. **Usa valores diferentes** para desarrollo y producción

4. **El frontend público solo necesita** `NEXT_PUBLIC_CHAT_API_URL`. Los secretos
   `PROMPTION_ADMIN_API_KEY` y `CHAT_SERVICE_TOKEN` viven server-side en Vercel.

5. **El backend necesita todas las variables** including API keys

## 🧪 Desarrollo Local

Para desarrollo local, crea un archivo `.env.local`:

```bash
# Backend (para el servidor FastAPI si lo ejecutas localmente)
PIF_API_URL=http://localhost:8000
PROMPTION_API_KEYS=tenant123.unitru:pk-123-tenant123.unitru
PROMPTION_ADMIN_API_KEYS=promption-platform:pk-admin-local-dev
GROQ_API_KEY=gsk_tu_key_local
OPENROUTER_API_KEY=sk-or-tu_key_local
GEMINI_API_KEY=tu_gemini_key_local
GEMINI_MODEL=gemini-3.1-flash
LLM_PROVIDER_ORDER=gemini,groq,openrouter

# Frontend (Next.js)
NEXT_PUBLIC_CHAT_API_URL=http://localhost:8001
PIF_API_URL=http://localhost:8000
PROMPTION_ADMIN_API_KEY=pk-admin-local-dev
CHAT_SERVICE_TOKEN=secreto-local
SESSION_SECRET=otro-secreto-local
```

## 🔍 Verificación

Después del despliegue, verifica:

1. **Backend**: 
   - `curl https://promption.onrender.com/api/v1/health`
   - Debe retornar estado saludable

2. **Frontend**:
   - Visita https://promptionsi.vercel.app/
   - El chat debe funcionar
   - El panel admin debe cargar logs

3. **Comunicación**:
   - El frontend debe poder conectar con el backend
   - Las API keys deben funcionar
