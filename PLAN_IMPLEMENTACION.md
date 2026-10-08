# Plan secuencial: corregir siete hallazgos de Promption

## Instrucción para el agente

Implementa exclusivamente estos siete puntos en el orden indicado. Completa cada corrección y sus pruebas específicas antes de continuar. Sigue AGENTS.md y preserva cambios del usuario. No añadas CI, staging, nuevas capas de detección, comparaciones de modelos ni rediseños generales. No despliegues ni ejecutes llamadas de pago.

Mantén OR entre capas ejecutadas, ACL e historial independientes y Output Guard obligatorio para incertidumbre. Conserva aliases src/, carga de configuración mediante promption/utils/config.py y columnas fijas del CSV. Añade metadatos en JSON/manifiestos separados. Prueba con artefactos temporales sin sobrescribir modelos/resultados oficiales. Justifica y declara dependencias necesarias.

## 1. Corregir ASR y distinguir proxy de evaluación real

Archivos: promption/benchmark/metrics.py, runner.py, tests/test_benchmark.py y consumidores del dashboard/reportes.

1. Calcular ASR solo sobre filas maliciosas (label == 1) con resultado evaluado válido: ataques exitosos / ataques evaluados.
2. Contar ataques bloqueados en entrada como prevenidos en evaluación del pipeline. No contar errores de generación como respuestas seguras; reportar errores y cobertura por separado.
3. Identificar modo proxy sin LLM y modo real con LLM en metadatos. No mezclar ambos si el proveedor falla durante una ejecución. Mantener columnas CSV y asociar evidencia de evaluación/error por id en metadatos cuando haga falta.
4. Corregir n_llm_queries para contar llamadas reales, no campos proxy no nulos. Separar llamadas de número de casos.
5. Cuando no hay ataques evaluados, informar ASR no disponible. Adaptar cálculo de reducción, dashboard y reportes.
6. Versionar métricas y leer resultados históricos sin reinterpretarlos o sobrescribirlos silenciosamente.

Verificar: añadir benignos no cambia ASR; 3 éxitos entre 10 ataques es 30 %; cero ataques y errores no generan cifras engañosas; conteos coinciden con proveedor simulado. Con los resultados actuales sin LLM, el proxy entre ataques debe ser 100 % → aproximadamente 12,64 %, no 45,71 % → 5,78 %.

Terminado: denominador correcto y proxy claramente identificado en todos los consumidores.

## 2. Retirar el umbral inefectivo de la API

Decisión: retirar threshold de la petición de filtrado. Mantener umbrales efectivos del servidor/tenant. No mapearlo silenciosamente a ML ni recuperar mezcla ponderada como criterio de bloqueo.

Archivos: promption/api/models.py, routes.py, filter/ensemble_filter.py, clientes, SDK, dashboard y tests/test_tenant_auth.py.

1. Localizar consumidores de FilterRequest.threshold, final_override y final_threshold.
2. Retirar override de petición y actualizar consumidores internos.
3. Rechazar explícitamente solicitudes que aún envíen threshold con error de validación y guía de migración. No permitir que Pydantic lo ignore silenciosamente.
4. Eliminar el umbral final inefectivo de configuración activa, caché y respuestas. Si compatibilidad pública exige conservar algún campo temporalmente, marcarlo obsoleto y no anunciarlo como umbral aplicado.
5. Mostrar umbrales realmente utilizados; validar rangos, valores finitos y relaciones de umbrales por tenant.
6. Documentar únicamente esta migración.

Verificar: threshold rechazado; umbrales efectivos cambian casos de frontera; veto OR se conserva; cambios de un tenant no afectan a otro; respuestas no muestran límites inefectivos.

Terminado: API, configuración y decisión coinciden.

## 3. Separar entrenamiento, validación y prueba por familias

Archivos: promption/training/dataset.py, split.py, train.py, train_lightweight.py y selección de datos del benchmark.

1. Auditar duplicados, originales, traducciones y variantes; comprobar contaminación sin asumirla.
2. Conservar identificador de origen y family_id/group_id en metadatos internos. Propagar grupos a traducciones. Para datos históricos, agrupar duplicados normalizados y revisar candidatos próximos antes de consolidarlos.
3. Crear train/validation/test deterministas por grupo, inicialmente 70/15/15, ajustando solo si el corpus no permite representación adecuada de etiquetas/idiomas.
4. Reservar adicionalmente fuentes completas para evaluación externa, excluidas de entrenamiento y selección. Un grupo que cruza fuentes debe quedar entero en una partición o excluirse con motivo registrado.
5. Guardar manifiesto de ids, grupos, particiones, fuentes, semilla y hash. Entrenamiento y benchmark deben usar el mismo manifiesto.
6. Ajustar vectorizadores/modelo solo con train; seleccionar parámetros y umbrales con validation; evaluar finalmente con test y fuentes externas por separado.
7. Benchmark independiente usa test por defecto. Corpus completo queda como modo exploratorio explícito.
8. Modelos antiguos sin manifiesto no pueden anunciar evaluación independiente; exigir regeneración o permitir solo análisis exploratorio etiquetado.
9. Adaptar consumidores sin cambiar columnas CSV.

Verificar: cero grupos compartidos; traducciones juntas; fuentes externas excluidas del ajuste; manifiesto reproducible; benchmark no contiene train/validation; modelo sin manifiesto no se presenta como holdout comprobado.

Terminado: se demuestra qué vio el modelo y las métricas de evaluación usan datos reservados.

## 4. Limitar entradas, cuerpo HTTP, concurrencia y cuotas

Archivos: modelos/rutas de Filter API y Chat Service, configuración. Revisar también límites ya existentes del servidor/hosting.

1. Añadir límites configurables validados: punto de partida de 100.000 caracteres por texto, 128 mensajes y 100.000 caracteres acumulados de historial, 2 MiB de cuerpo JSON. Ajustar únicamente por usos legítimos documentados.
2. Acotar roles, identificadores y contexto. Rechazar exceso sin truncar contenido que debe inspeccionarse.
3. Limitar bytes antes de deserialización, incluso sin Content-Length. Devolver 413 por cuerpo excesivo.
4. Aplicar cuotas por tenant autenticado y endpoint; separar benchmark/tareas costosas. Punto de partida: 60 solicitudes/minuto por endpoint de protección y 1 benchmark/hora por tenant, configurables.
5. Con varios workers/réplicas, usar contadores compartidos; no presentar contadores locales como cuota global. Reutilizar backend compartido del punto 6 cuando corresponda; dejar interfaz preparada y completar integración allí.
6. Limitar concurrencia y espera: inicialmente 4 operaciones de protección y 1 benchmark por proceso, cola acotada. Aclarar alcance por proceso; impedir que benchmark agote capacidad normal.
7. Acotar sample_size y trabajo por benchmark. Aplicar timeout a llamadas externas. No afirmar que cancelar una espera detiene trabajo síncrono ya iniciado.
8. Devolver 429 y Retry-After por cuota; error estable por saturación compatible con clientes existentes.

Verificar: cuerpos con/sin Content-Length; texto/historial excesivos; cuotas aisladas por tenant; concurrencia y cola acotadas; benchmark no monopoliza protección; alcance compartido probado al integrar punto 6.

Terminado: entradas acotadas y cuotas/cupos con alcance explícito y verificable.

## 5. Hacer observables los fallos ML

Archivos: promption/filter/ensemble_filter.py, ml_filter.py, ml_filter_lightweight.py, health y logging existente.

1. Distinguir modelo ausente, fallo de carga y fallo de inferencia en ambos backends.
2. Corregir backend ligero: un fallo de inferencia no puede devolverse como probabilidad 0 válida. Propagar error tipado o resultado explícitamente no disponible.
3. Conservar degradación: ausencia de modelo manejable, veto heurístico bloquea e incertidumbre sin ML requiere Output Guard. Error no equivale a benigno.
4. Distinguir ML omitido por ruta benigna/veto de ML intentado y fallido.
5. Exponer estado/código de causa en metadatos/health y contadores existentes.
6. Emitir WARNING/ERROR sanitizados por cambios de estado y registrar recuperación, evitando alertas repetidas por petición. No volcar excepciones que puedan contener prompt o secretos.
7. Preparar condición de alerta para fallos persistentes mediante mecanismo existente. Si no hay receptor configurado, reportarlo; no crear un servicio externo ni fingir notificaciones operativas.

Verificar: ausencia, artefacto corrupto, inferencia fallida, recuperación, ruta omitida y logs sin contenido sensible. Especialmente: fallo ligero nunca aparece como predicción válida de probabilidad 0.

Terminado: fallo observable y degradación segura sin clasificación benigna ficticia.

## 6. Compartir historial/estado y escribir atómicamente

Archivos: promption/conversation.py, state.py y adaptadores/configuración del Chat Service.

1. Identificar historial visible, evidencia de seguridad y controles necesarios. Mantener aislamiento por tenant, usuario, roles y conversación.
2. Conservar memoria/JSON solo como modo explícito de un proceso.
3. Implementar backend compartido configurable; si no existe uno adecuado, usar Redis y justificar/declarar dependencia. Reutilizarlo para cuotas del punto 4. No contratar ni desplegar infraestructura.
4. Actualizar historial y evidencia con operaciones atómicas, TTL y límites existentes. Evitar read-modify-write sin transacción/control de versión.
5. Guardar controles administrativos y auditoría con versión y actualización atómica. Fallo de persistencia no puede devolverse como éxito.
6. En JSON local, escritura temporal y sustitución atómica; no afirmar que lock de hilos protege entre procesos.
7. Definir persistencia/recuperación para reinicios. No tratar controles como caché evictable sin recuperación segura.
8. Ante pérdida/indisponibilidad de evidencia requerida, bloquear o exigir nueva conversación. No continuar silenciosamente con historial parcial. Controles irrecuperables adoptan estado seguro.
9. Configurar Chat Service para backend seleccionado e impedir modo local incompatible con despliegue declarado de varios workers/réplicas.

Verificar: dos instancias comparten historial/controles/cuotas; actualizaciones concurrentes no se pierden; TTL/aislamiento; errores de escritura; reinicio; evidencia ausente. Si no hay Redis disponible, probar lógica con backend controlado y reportar prueba real pendiente; no habilitar distribuido sin verificarlo.

Terminado: estado coherente entre procesos y backend local delimitado.

## 7. Exigir modo demo explícito para claves públicas

Archivos: promption/api/auth.py, arranque de API, config/tenants.yaml, configuración de despliegue y tests/test_tenant_auth.py.

1. Añadir PROMPTION_DEMO_MODE, desactivado por defecto.
2. Cargar claves públicas de tenants.yaml solo con demo explícita y sin registro de entorno efectivo. Conservar precedencia de credenciales de entorno.
3. Fuera de demo, validar al arrancar que existe registro válido. Ausencia, registro malformado o credenciales incompletas impiden que API quede operativa.
4. Rechazar demo en entorno declarado de producción. No imprimir claves en errores/logs.
5. Mantener scopes de consumidor/administrador y encabezados compatibles.
6. Actualizar instrucciones de demo y requisitos de despliegue sin añadir secretos.

Verificar: sin claves/sin demo arranque falla; demo explícita funciona; registro de entorno excluye claves públicas; configuración malformada rechazada; scopes preservados; errores no revelan claves.

Terminado: falta de configuración nunca activa automáticamente credenciales públicas.

## Entrega

Después de los siete puntos, ejecutar pruebas de AGENTS.md, incluyendo pytest y SDK, benchmark sin LLM con artefactos temporales y smoke de API/dashboard con modo de autenticación apropiado. No desplegar ni ejecutar benchmarks de pago.

Entregar tabla de siete puntos: corregido/pendiente, archivos afectados y prueba que lo demuestra. Señalar requisitos externos y checks no ejecutados. Documentar solo migraciones necesarias. No ampliar el alcance a un ciclo de desarrollo general.
