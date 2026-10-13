# Benchmark pareado: ejecución y límites

El runner conserva el recorrido Chat, Scope, RBAC y MCP. El baseline desactiva Input/Conversation y Output Guard en una instancia de prueba exclusiva. Las sondas `--probe-filter` son consultas independientes, no trazas de la primera capa que vetó el chat.

`requirements-benchmark.txt` incluye psutil, ya utilizado por el backend, para esperar la muerte del proceso padre de forma multiplataforma. No se utilizan señales de existencia de PID que puedan confundir permisos con muerte del proceso.

## Reintentos y consumo

Los POST con HTTP 408/500/502/503/504 y desconexiones de resultado ambiguo no se repiten por defecto. `--retry-ambiguous` permite repetirlos explícitamente, con riesgo de ejecución duplicada y facturación adicional. Los HTTP 429 y fallos de conexión previos al envío conservan los reintentos acotados y Retry-After.

`--max-provider-calls` es un presupuesto orientativo de intentos reportados por el backend. `--provider-call-reservation N` reserva N intentos por chat en curso para evitar que varias sesiones ignoren simultáneamente el saldo pendiente. Ninguna reserva garantiza un tope de facturación: una petición puede realizar más intentos internamente. Una respuesta con número de llamadas desconocido detiene la programación de nuevos chats; el caso queda registrado, no se interpreta como consumo cero.

`execution-status.json` distingue COMPLETE e INCOMPLETE, cantidades ejecutadas y pendientes, detención por presupuesto, llamadas desconocidas y restauración verificada. Una ejecución incompleta devuelve código 2. Los fallos de ejecución o restauración siguen siendo errores; no deben interpretarse como un benchmark terminado.

## Latencia y versiones

Los CSV conservan `chat_client_latency_ms` y añaden `client_throttle_ms`, `client_backoff_ms` y `http_attempts_latency_ms`. El primero incluye toda la espera observada por el cliente. Los tiempos de etapas provienen del backend. No sumar percentiles de etapas para obtener un percentil global.

Antes de ejecutar se consulta `/status` y se guarda `execution-fingerprint.json`: modelo/proveedores configurados, versión publicada del servicio, políticas y hashes de código, configuración y artefactos ML locales. La reanudación rechaza diferencias. Los hashes locales no certifican el código de un servidor remoto: para un estudio remoto debe archivarse además su versión de despliegue y configuración efectiva. `actual_model` por respuesta conserva el modelo reportado; el modelo configurado puede diferir del utilizado en una respuesta con herramientas.

El cambio del runner invalida el hash de manifiestos anteriores para `--resume`. Utilizar una carpeta nueva para próximas ejecuciones o el runner archivado para continuar una anterior. `--reprocess-only` sigue disponible sin nuevas llamadas.

## Evidencia y recuperación

La corrupción JSON intermedia produce error. Una última línea incompleta puede recuperarse al reanudar: se conserva una copia íntegra de evidencia y se elimina únicamente la escritura truncada antes de añadir eventos.

Un supervisor externo se inicia y confirma disponibilidad antes de activar baseline. Si muere el runner, el supervisor intenta activar ambos guards, verifica sus estados y guarda `watchdog-restoration.json`. `--no-watchdog` desactiva esa protección explícitamente. Se incluye una prueba real de muerte de proceso con un servidor local simulado.

Ctrl+C y SIGTERM solicitan detención: las sesiones pendientes dejan de enviarse y se espera a las llamadas ya iniciadas antes de restaurar controles. La terminación forzada de Windows utiliza el supervisor, porque no garantiza ejecución de los manejadores de señales Python.

El supervisor no puede operar con el equipo apagado, si también se termina su proceso o si el servicio está permanentemente inaccesible. En esos casos se necesita restauración al arranque del servicio o una concesión con expiración implementada en el backend. No ejecutar baseline contra un servicio compartido de producción. El comando `--restore-only` permite restauración manual.

## Interpretación

Un bloqueo por alcance/RBAC no demuestra detección de inyección. Un ataque no bloqueado no demuestra cumplimiento ni fuga, y una solicitud benigna permitida no demuestra calidad funcional. Los intervalos Wilson no corrigen dependencia entre variantes de la misma familia.

El ensayo de canarios utiliza el evaluador independiente `leakage_canary_evaluator.py`. El canario ficticio debe instalarse privadamente antes del experimento. No basta con proporcionarlo al runner. El evaluador observa señales en respuestas; no certifica ausencia de exfiltración por herramientas o redes externas.
