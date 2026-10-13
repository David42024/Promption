# Corrección y validación local de permisos, alcance y puente

Se ajustaron reglas de recursos para distinguir definiciones y disponibilidad cualitativa de inventario privado; se añadieron capacidades de alcance derivadas de los roles y políticas de la aplicación. Los rechazos del puente conservan dirección, motivo y política, y la captura de uso del proveedor ocurre antes de la inspección final cuando ese uso está disponible. Ningún umbral ML ni control de producción fue deshabilitado.

## Evidencia real

El piloto original tuvo 6 bloqueos entre 14 consultas benignas. Una repetición intermedia de los mismos 20 casos redujo los bloqueos benignos a 1; se identificó otra regla demasiado amplia sobre la expresión «stock actual». La versión actual distingue esa mención general de campos concretos y referencias a inventario empresarial.

La comprobación final repitió exactamente los 6 casos originales que se bloquearon: laptop, tres consultas de disponibilidad conceptual, definición de stock y listado VIP por admin. Resultado: 6 respuestas autorizadas, 0 bloqueos falsos, 0 errores HTTP, 18 llamadas al proveedor, 48.906 tokens conocidos y uso completo en los 6 casos. Modelo configurado: gpt-5.4-nano.

Controles negativos reales: inventario privado por customer, listado VIP por customer y credenciales críticas por admin. Los 3 se rechazaron antes del proveedor, con 0 llamadas LLM.

Estas cifras son regresiones funcionales locales, no una estimación general de FPR ni una certificación de seguridad. La última comprobación selecciona los casos anteriormente fallidos; no constituye una nueva muestra aleatoria. No hay brazo sin protección ni canario de confidencialidad instalado. Incubunt y producción no fueron desplegados ni certificados en esta tarea.

La repetición intermedia completa aún registró una consulta en inglés con uso parcial: debe seguir reportándose como null para el total y con subtotales conocidos. La captura añadida no inventa métricas que una etapa no entrega.

## Artefactos

- Original: `data/results/validation/full-chat-pilot-20-20261009-160556-6b5f7f/`.
- Repetición intermedia: `data/results/validation/full-chat-pilot-final-20261009-163401-0e47a4/`.
- Seis regresiones con código actual: `data/results/validation/six-original-blocks-recheck-20261009-163919/`.
- Controles negativos: `data/results/validation/guard-negative-checks-20261009-163546/`.

Se mantienen evidencias, CSV y resúmenes sin sobrescribir el benchmark oficial. Las pruebas de latencia coincidieron con ejecuciones de tests offline: no utilizar esta comparación como un estudio formal de rendimiento.
