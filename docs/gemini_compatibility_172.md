# Gemini y herramientas en Promption 1.7.2

## Corrección de interoperabilidad

La prueba con Gemini 3.5 Flash-Lite detectó un HTTP 400 al continuar una llamada a herramienta sin su firma de contexto. Google documenta estas firmas como parte del estado del modelo. La evaluación utiliza ahora el [proveedor oficial de Google para AI SDK](https://ai-sdk.dev/providers/ai-sdk-providers/google), versión `@ai-sdk/google@3.0.138`, compatible con el AI SDK 6 del proyecto.

Promption sigue eliminando los metadatos de proveedor de las salidas públicas. La versión 1.7.2 mantiene una caché privada por instancia de middleware para las firmas de llamadas a herramientas autorizadas. Solo las restituye en una petición interna al proveedor cuando coinciden el identificador, el nombre y los argumentos de la llamada. No acepta una firma aportada por el cliente ni la restituye para una herramienta sin permiso.

La caché conserva como máximo 32 entradas, limita cada firma a 65.536 caracteres y los argumentos canonicalizados a 32.768. No se serializa al cliente. El modelo envuelto debe reutilizarse durante los pasos de una misma ejecución de herramientas.

Los controles de entrada, contexto, permisos y salida siguen ejecutándose. Esta corrección no cambia sus umbrales, etiquetas, pesos del clasificador ni reglas de detección.

## Proveedor de investigación

La dependencia de Google pertenece al paquete privado de [scripts de investigación](../scripts/research/package.json); la librería reutilizable conserva su independencia del proveedor. El paquete y su lockfile fijan la versión instalada.

La adaptación anterior por compatibilidad OpenAI se conserva como piloto incompleto. La evaluación nativa comienza con respuestas nuevas en las tres condiciones y registra por separado sus fallos operativos.

Las pruebas sintéticas verificaron el ciclo completo de herramienta, resultado y respuesta, la clasificación estructurada y la ausencia de firmas privadas en la salida pública. El registro de consumo rechaza el marcador de omisión de validación de firmas y herramientas nativas adicionales que podrían generar cargos.

## Validación local

- Python: 1.242 pruebas aprobadas y 10 omitidas.
- SDK: 178 pruebas aprobadas, incluidas cuatro pruebas de firmas y streaming.
- Control de consumo: 10 pruebas aprobadas.
- Comprobación de tipos TypeScript aprobada.
- Benchmark local sin LLM ni entrenamiento completado; sus métricas proxy no son resultados de exfiltración.
- API y dashboard: comprobaciones HTTP 200; AppTest del dashboard aprobado.

## Datos y nivel gratuito

El usuario autorizó expresamente el envío del corpus depurado después de conocer el tratamiento de datos del nivel gratuito. Se utilizan conversaciones seudonimizadas y una clave sintética. La comprobación local de los 120 casos no encontró la clave real ni representaciones conocidas de ella.

Google puede utilizar las entradas y salidas de los servicios gratuitos para mejorar sus productos y someterlas a revisión humana, según sus [términos de Gemini](https://ai.google.dev/gemini-api/terms). El campo OpenAI `store` no está disponible en esta integración y no se presenta como una forma de desactivar ese tratamiento.

La contabilidad de esta ejecución aplica la tarifa gratuita solicitada por el usuario. La API no certifica por sí sola el estado de facturación del proyecto; las cifras calculadas no sustituyen una factura ni una comprobación de AI Studio. No se configura facturación ni un proveedor alternativo de pago.

La clave de API se guarda únicamente en `.env.gemini.local`, con permisos `0600` y exclusión explícita de Git. Las solicitudes, respuestas y firmas de protocolo permanecen en el directorio privado de resultados. Los informes públicos contienen agregados y hashes.
