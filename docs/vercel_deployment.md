# Despliegue en Vercel - Guía de Configuración

## Arquitectura para Múltiples Usuarios Concurrentes

El sistema está diseñado para soportar múltiples usuarios concurrentes en Vercel con las siguientes características:

### 1. Arquitectura Separada

**Backend (Filter API):**
- FastAPI que corre en un servidor separado (no en Vercel)
- Gestiona el estado de los logs en memoria (thread-safe)
- Soporta múltiples requests concurrentes

**Frontend (Demo Shop):**
- Next.js desplegado en Vercel
- Stateless (no mantiene estado local)
- Se comunica con el Filter API vía HTTP

### 2. Sistema de Logs Estructurados

El sistema implementa logs estructurados en formato JSON que soportan concurrencia:

- **Thread-safe**: Usa `threading.Lock()` para proteger el acceso a los logs
- **En memoria**: Mantiene los últimos 1000 logs en memoria para acceso rápido
- **Persistencia**: También escribe logs en archivo JSONL para respaldo
- **Filtrado**: Permite filtrar por nivel, categoría, tenant, usuario, y tiempo

### 3. Variables de Entorno Requeridas

**Para el Frontend (Vercel):**
```env
PIF_API_URL=https://tu-filter-api.com
PIF_TENANT_KEY=pif_demo_shop_123456
PIF_TENANT_ID=demo-shop
GROQ_API_KEY=gsk_tu_clave_real
PIF_LLM_MODEL=openai/gpt-oss-20b
PIF_ADMIN_SECRET=tu_secreto_admin_seguro
```

**Para el Backend (Filter API):**
```env
PIF_ADMIN_SECRET=tu_secreto_admin_seguro
PIF_API_KEYS=demo-shop:pif_demo_shop_123456,otro-tenant:otro_key
GROQ_API_KEY=gsk_tu_clave_real
```

## Despliegue en Vercel

### Paso 1: Preparar el Backend

El Filter API debe desplegarse en un servidor separado (no Vercel) porque:

1. Requiere dependencias pesadas (sentence-transformers, torch)
2. Necesita persistencia de logs en disco
3. Requiere tiempo de ejecución prolongado

**Opciones de despliegue del backend:**
- Railway, Render, AWS EC2, Google Cloud Run, o tu propio VPS

### Paso 2: Configurar el Frontend para Vercel

1. **Crea un archivo `.env.local` en el directorio `demo/`:**
```env
PIF_API_URL=https://tu-filter-api.com
PIF_TENANT_KEY=pif_demo_shop_123456
PIF_TENANT_ID=demo-shop
GROQ_API_KEY=gsk_tu_clave_real
PIF_LLM_MODEL=openai/gpt-oss-20b
PIF_ADMIN_SECRET=tu_secreto_admin_seguro
```

2. **Agrega las variables de entorno en Vercel:**
   - Ve a tu proyecto en Vercel
   - Settings > Environment Variables
   - Agrega todas las variables del `.env.local`

3. **Despliega:**
```bash
cd demo
vercel --prod
```

### Paso 3: Configurar el Dominio del Backend

Asegúrate de que el Filter API sea accesible desde Vercel:

- Usa HTTPS (requerido para Vercel)
- Configura CORS si es necesario
- Asegúrate de que el puerto sea accesible (usualmente 443 o 80)

## Panel de Administración

### Acceso

El panel de admin está disponible en: `https://tu-demo.vercel.app/admin`

### Autenticación

El panel requiere la variable `PIF_ADMIN_SECRET` para acceder a los logs de la API.

**IMPORTANTE:** Cambia el valor por defecto en producción.

### Funcionalidades

1. **Ver logs en tiempo real**
   - Filtrar por nivel (INFO, WARNING, ERROR)
   - Filtrar por categoría (filter, authorization, output_guard)
   - Filtrar por tenant
   - Limitar número de resultados

2. **Estadísticas**
   - Total de logs
   - Logs de las últimas 24 horas
   - Tenants activos
   - Distribución por nivel y categoría

3. **Monitor de decisiones**
   - Ver cómo cada capa del filtro decide
   - Auditoría de accesos autorizados/bloqueados
   - Detección de patrones de ataque

## Limitaciones de Concurrencia

### 1. Logs en Memoria

Los logs se mantienen en memoria del servidor del Filter API. Si tienes múltiples instancias del backend (load balancing), cada instancia tendrá sus propios logs.

**Solución:** Implementa un sistema de logs centralizado (ej. Elasticsearch, Loki) para producción.

### 2. Estado del Chat

El estado del chat (mensajes) se mantiene en localStorage del navegador. Si el usuario cambia de dispositivo, pierde el historial.

**Solución:** Implementa backend de chat con persistencia en base de datos.

### 3. Rate Limiting

Actualmente no hay rate limiting implementado. Para producción, considera agregar:

- Rate limiting por IP
- Rate limiting por usuario
- Rate limiting por tenant

## Seguridad en Producción

1. **Cambia todas las keys por defecto**
2. **Usa HTTPS para todas las conexiones**
3. **Implementa autenticación robusta para el panel admin**
4. **Agrega rate limiting**
5. **Monitorea los logs regularmente**
6. **Implementa alertas para actividades sospechosas**

## Escalado

Para soportar más usuarios:

1. **Escalado horizontal del Filter API**
   - Usa load balancing
   - Implementa logs centralizados
   - Considera Redis para caché compartida

2. **Optimización del modelo ML**
   - Usa modelos más pequeños
   - Implementa caché de embeddings
   - Considera batch processing

3. **CDN para estáticos**
   - Vercel ya hace esto automáticamente
   - Considera CDN para los modelos si se sirven estáticamente

## Monitoreo

Usa el panel de admin para:

- Monitorear la tasa de bloqueos
- Detectar patrones de ataque
- Ver el rendimiento de cada capa
- Identificar tenants con alta actividad

Considera integrar con herramientas de monitoreo como:

- Sentry para error tracking
- Grafana para métricas
- Prometheus para alertas
