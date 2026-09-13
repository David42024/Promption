# Configuración de Variables de Entorno para Producción

## 🌐 URLs de Producción
- **Backend (Render)**: https://promption.onrender.com/
- **Frontend (Vercel)**: https://promptionsi.vercel.app/

## 🔧 Configuración en Render (Backend)

Las siguientes variables deben configurarse en el dashboard de Render:

### Variables de Entorno para Render
```
PIF_API_URL=https://promption.onrender.com
PIF_TENANT_KEY=pif_demo_shop_123456
PIF_TENANT_ID=demo-shop
GROQ_API_KEY=gsk_TU_GROQ_KEY_REAL
OPENROUTER_API_KEY=sk-or-TU_OPENROUTER_KEY_REAL
GEMINI_API_KEY=TU_GEMINI_KEY_REAL
GEMINI_MODEL=gemini-3.1-flash
LLM_PROVIDER_ORDER=gemini,groq,openrouter
PIF_LLM_MODEL=llama-3.1-70b-versatile
PIF_ADMIN_SECRET=TU_SECRET_SUPER_SEGuro_PROD
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
NEXT_PUBLIC_PIF_API_URL=https://promption.onrender.com
NEXT_PUBLIC_PIF_ADMIN_SECRET=TU_SECRET_SUPER_SEGuro_PROD
```

### Pasos para configurar en Vercel:
1. Ve a tu dashboard de Vercel
2. Selecciona tu proyecto
3. Navega a "Settings" → "Environment Variables"
4. Añade cada variable de entorno con su valor correspondiente
5. Haz "Redeploy" para aplicar los cambios

## ⚠️ IMPORTANTE: Seguridad

1. **CAMBIA los valores por defecto**:
   - `PIF_ADMIN_SECRET` debe ser un string aleatorio largo
   - `PIF_TENANT_KEY` debe ser único para tu tenant

2. **Nunca commits secrets reales** en el repositorio

3. **Usa valores diferentes** para desarrollo y producción

4. **El frontend solo necesita**:
   - `NEXT_PUBLIC_PIF_API_URL` (URL del backend)
   - `NEXT_PUBLIC_PIF_ADMIN_SECRET` (para el panel admin)

5. **El backend necesita todas las variables** including API keys

## 🧪 Desarrollo Local

Para desarrollo local, crea un archivo `.env.local`:

```bash
# Backend (para el servidor FastAPI si lo ejecutas localmente)
PIF_API_URL=http://localhost:8000
PIF_TENANT_KEY=pif_demo_shop_123456
PIF_TENANT_ID=demo-shop
GROQ_API_KEY=gsk_tu_key_local
OPENROUTER_API_KEY=sk-or-tu_key_local
GEMINI_API_KEY=tu_gemini_key_local
GEMINI_MODEL=gemini-3.1-flash
LLM_PROVIDER_ORDER=gemini,groq,openrouter
PIF_LLM_MODEL=llama-3.1-70b-versatile
PIF_ADMIN_SECRET=admin_secret_change_me

# Frontend (Next.js)
NEXT_PUBLIC_PIF_API_URL=http://localhost:8000
NEXT_PUBLIC_PIF_ADMIN_SECRET=admin_secret_change_me
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
