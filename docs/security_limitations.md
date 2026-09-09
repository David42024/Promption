# Limitaciones de Seguridad Conocidas

## Defensa en Profundidad Implementada

El sistema de seguridad de Demo Shop implementa múltiples capas de protección contra fugas de credenciales:

1. **Autorización de Endpoints por Rol** (`src/api/authorization.py`)
   - Allowlist explícita de endpoints permitidos por rol
   - Bloqueo de patrones sensibles (`/credentials`, `/apikey`, `/password`, etc.)
   - Validación antes de ejecutar llamadas a API

2. **Autorización de MCP Tools** (`demo/lib/mcp.js`)
   - Validación de roles antes de ejecutar tools
   - Detección de patrones sensibles en nombres/descripciones de tools
   - Logging seguro de intentos de autorización

3. **Output Guard** (`src/output_guard/`)
   - Escaneo de respuestas del LLM antes de entregarlas
   - Detección de patrones de credenciales (API keys, JWTs, private keys, connection strings)
   - Política PASS/REDACT/BLOCK según severidad
   - Logging seguro sin valores en claro (solo fingerprints SHA256)

## Limitaciones Conocidas

### 1. Paráfrasis y Troceado de Secretos

**Problema**: El Output Guard detecta secretos basándose en patrones estructurales y entropía. Si el LLM parafrasea o trocea un secreto en la respuesta, es posible que el patrón no sea detectado.

**Ejemplos de casos que podrían pasar el filtro**:
- "La clave es la primera parte de un código que empieza por XYZ y termina por ABC"
- "Usa las letras: X-Y-Z-1-2-3 separadas por guiones"
- El modelo revela el secreto carácter por carácter en múltiples respuestas

**Mitigación actual**:
- Patrón de "proximidad" que detecta palabras clave cerca de valores de alta entropía
- Bloqueo de endpoints sensibles en la capa de autorización (previene acceso a la fuente)
- Logging de todos los intentos bloqueados para auditoría

**Mitigación futura recomendada**:
- Implementar detección basada en contexto semántico
- Historial de conversación para detectar patrones de revelación progresiva
- Rate limiting en endpoints sensibles

### 2. Codificación y Ofuscación

**Problema**: Los secretos codificados en base64, hex, u otros formatos pueden no ser detectados por los patrones actuales.

**Ejemplos**:
- "Usa este valor en base64: YXBpX2tleV92YWx1ZQ=="
- "La clave en hexadecimal es 41 50 49 5F 4B 45 59"

**Mitigación actual**:
- Ninguna específica para estos casos

**Mitigación futura recomendada**:
- Decodificar base64/hex en el escaneo antes de aplicar patrones
- Detectar cadenas que parecen datos codificados

### 3. Contexto Multilingüe

**Problema**: Los patrones actuales están optimizados para español e inglés. Otros idiomas pueden tener variaciones en palabras clave.

**Mitigación actual**:
- Patrones básicos en español e inglés
- Validación estructural (formato JWT, private keys) que es idioma-independiente

### 4. Secretos Legítimos en Contexto

**Problema**: Hay casos donde usuarios legítimos necesitan ver ciertos secretos (ej. admin configurando integraciones).

**Mitigación actual**:
- Allowlist de endpoints por rol
- Bloqueo solo de patrones de credenciales críticas
- Admin puede acceder a configuración no sensible

**Recomendación**:
- Implementar flujos de aprobación explícitos para acceso a secretos
- Auditoría detallada de accesos a datos sensibles

## Recomendaciones de Seguridad

1. **Nunca depender de una sola capa**: La defensa en profundidad es esencial. Si una capa falla, las otras deben proteger.

2. **Auditoría continua**: Revisar regularmente los logs de autorización y Output Guard para detectar patrones de ataque.

3. **Actualización de patrones**: Mantener los patrones del Output Guard actualizados con nuevos formatos de credenciales.

4. **Rate limiting**: Implementar límites de tasa en endpoints sensibles para prevenir ataques de fuerza bruta.

5. **Monitoreo de anomalías**: Implementar detección de anomalías en patrones de acceso a datos.

## Estado de Implementación

- ✅ Autorización de endpoints por rol
- ✅ Detección de patrones sensibles en MCP tools  
- ✅ Output Guard con múltiples patrones de credenciales
- ✅ Logging seguro de intentos bloqueados
- ✅ Tests de integración para casos comunes
- ⚠️ Mitigación limitada de paráfrasis/troceado
- ⚠️ Sin detección de codificación/ofuscación
- ⚠️ Patrones principalmente en español/inglés

## Contacto

Para reportar nuevas vulnerabilidades o sugerir mejoras, revisa el repositorio del proyecto.
