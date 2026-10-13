# Entrega de infraestructura científica V9

## Alcance realizado

Se añadieron tres scripts, una suite de pruebas, dos fixtures/declaraciones y la guía de protocolo. **Cero archivos de producción modificados.** No se reentrenó el modelo, cambiaron umbrales/reglas/RBAC ni se llamó a OpenAI. No se inició una ejecución pagada de 4.000 recorridos.

El runner existente, su transporte HTTP, recuperación/watchdog, clasificador de resultados, esquema CSV, evaluador de canarios, verificador de familias y backend SQLite se reutilizan. El adaptador añade controles de congelamiento por bloque, restauración entre brazos, presupuestos de lease y la negativa a repetir POST de resultado incierto. Los archivos nuevos no sustituyen el runner histórico ni sus resultados.

Se implementó comparación con identidad igual y transcript revisado igual, sesiones distintas y comprobación del historial que observa realmente Chat Service. Esto define un ensayo condicionado a un diálogo fijo; no afirma equivalencia de trayectorias adaptativas. Se requieren backends locales dedicados y SQLite para los turnos con historia. No se habilita baseline en producción compartida.

## Verificación ejecutada

| Comprobación | Resultado |
|---|---:|
| Python completo, excluyendo live_llm | 1.245 aprobadas, 9 deseleccionadas |
| Subtests existentes | 16 aprobados |
| Advertencias heredadas | 8 de deprecación |
| Tests nuevos científicos | 23 aprobados, incluidos dentro del total |
| SDK JavaScript | 66 aprobados |
| Demo JavaScript | 81 aprobados |
| TypeScript estricto del SDK | Sin errores |
| compileall de los módulos añadidos | Sin errores |
| Preparación smoke sin red | 2 benignos + 2 ataques por brazo, 132 archivos congelados |
| Verificación del manifiesto smoke | Hashes y dependencias iguales |
| Reprocesamiento histórico | 80 respuestas, cero llamadas nuevas |

La fixture de canario usa el SDK oficial MCP: se verificaron lectura experimental admin, denegación a customer y vinculación del resultado autorizado al hash observado por el wrapper. **Esto no constituye exposición real a OpenAI ni integración de la fixture en Chat Service.**

Una primera prueba local detectó una firma de retorno sin tipar que MCP 2.x no acepta como structured output. Se corrigió únicamente la herramienta experimental a `dict[str, Any]` y se volvió a ejecutar la suite completa; el resultado final de arriba corresponde a esa corrección. La prueba existente del watchdog necesitó ejecución local fuera del sandbox para su servidor loopback; pasó sin llamadas externas.

## Evidencia conservada

- `data/results/scientific-suite-verified-20261012.log`: ejecución Python final, 131,41 s.
- `data/results/scientific-sdk-final-20261012.log` y `scientific-demo-final-20261012.log`: suites JavaScript.
- `data/results/scientific-smoke-prepared-20261012/experiment`: corpus, manifiesto y configuración declarada, sin eventos pagados.
- `data/results/scientific-v9-historical-final-20261012`: análisis nuevo de evidencia histórica; sus originales se conservaron.

El smoke tiene valores declarativos pendientes de completar en la configuración de ejemplo. Está preparado para verificar contratos, **no se presenta como backend real certificado**. Los 80 registros históricos pertenecen a un diseño anterior y no se transforman retroactivamente en holdout independiente ni diálogo pareado fijo. Las gráficas/CSV no reemplazan esa limitación.

## Límites pendientes antes del experimento final

1. Importar un holdout externo, con inventarios de desarrollo/regresión, familias, fuentes y revisión humana de paráfrasis/traducciones. No se fabricaron datos independientes.
2. Completar y archivar configuración efectiva del backend/SDK/Next/modelos/parámetros y datos MCP del proceso dedicado. Los hashes locales no atestan despliegues remotos.
3. Instalar la fixture de canario únicamente en un harness separado y observar su resultado en el payload real al proveedor. Las trazas de exposición y destinos aún no existen para el chat productivo; sin ellas el resultado es no evaluable.
4. Adjudicar calidad funcional con revisión ciega y referencias MCP. Ninguna respuesta se declara correcta por obtener HTTP 200.
5. Autorizar y ejecutar el smoke con OpenAI antes de aprobar el experimento completo. No hubo consumo pagado durante esta entrega.

Los informes separan SECURITY_BLOCK, POLICY_DENIAL, TECHNICAL_FAILURE, ALLOWED y UNKNOWN. No equiparan ausencia de veto con fuga, ni bloqueo administrativo con detección de inyección. Tokens desconocidos quedan null y subtotales conocidos se distinguen de totales exactos. Los intervalos por familias y McNemar exploratorio no justifican generalización si las fuentes no son independientes.

## Paquete y parche

`exports/scientific-evaluation-v9/parche_minimo.zip` contiene exclusivamente las incorporaciones de esta entrega, su diff de adición y manifiesto SHA-256. Requiere el proyecto V9 actual y los módulos reutilizados. No incluye `.env`, credenciales, pesos, bases de conversación ni evidencia cruda empresarial. No sobrescribe las modificaciones anteriores del repositorio.

La guía `docs/final_scientific_evaluation_v9.md` contiene preparación, smoke, ejecución de 1.000 + 1.000 por brazo, reanudación, adjudicación y reprocesamiento sin red. No se presentan métricas futuras como medidas.
