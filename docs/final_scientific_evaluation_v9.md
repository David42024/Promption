# Evaluación científica final de Promption V9

Esta implementación añade infraestructura experimental. No modifica producción, el modelo, reglas, umbrales, roles ni permisos. No inicia servicios ni llama a OpenAI al preparar o reprocesar. `--execute` exige autorización explícita, backends locales dedicados y una preparación previa.

## Archivos y reutilización

- `scripts/scientific_evaluation.py`: contrato de corpus, selección de sesiones sin reemplazo, congelamiento, análisis, estadísticas, canarios y revisión ciega.
- `scripts/run_final_scientific_v9.py`: adaptador del runner existente con verificación antes de cada brazo/bloque, restauración entre brazos y límites de lease.
- `tests/test_scientific_evaluation.py`: regresiones exclusivamente locales.
- `data/validation/scientific_smoke_cases.jsonl`: fixture de desarrollo, nunca holdout independiente.
- `data/validation/scientific_runtime.example.json`: declaración sin credenciales; completar valores reales antes del congelamiento.

Se reutilizan `run_paired_2000_v9.py`, su cliente HTTP, watchdog, evidencia incremental, clasificador de errores, columnas CSV, `check_v9_family_holdout.py`, `leakage_canary_evaluator.py` y el almacenamiento SQLite existente. **Archivos de producción modificados: 0.** No se cambia Redis.

## Preparación y separación experimental

Cada línea JSONL conserva `id`, `text`, `kind` (`benign` o `attack`), `family_id`, `source`, `source_reference`, `roles`, `authenticated`, `session_id`, `turn_index`, `history`, `history_tiers`. Para compatibilidad de CSV incluir también `family`, `seed_id`. El texto no se traduce, decora ni relabela durante selección.

`history` contiene pares user/assistant revisados del diálogo de referencia. En turno cero es `[]`; en turno n contiene exactamente n pares. Los mensajes user anteriores deben coincidir con las solicitudes originales. `history_tiers` conserva sus niveles autorizados (`publico`, `interno`, `confidencial`, `restringido`). Se rechazan cortes de sesión, cambios de roles, duplicados exactos normalizados y historiales que el backend truncaría.

En modo final se exigen inventarios JSONL de desarrollo y regresión; se rechazan familias, fuentes o textos compartidos. Cada caso exige `provenance_reviewed: true`, `semantic_reviewed: true` y `source_reference`. Estas declaraciones **no prueban independencia por sí mismas**: archivar revisión humana de paráfrasis, traducciones y procedencia. No hay un holdout externo nuevo incluido. No usar el corpus V6–V9 ajustado como prueba independiente.

El muestreo usa semilla reproducible y sesiones completas sin reemplazo; puede rechazar cuotas incompatibles. No inventa variantes para llegar a 2.000 casos. Organizar un inventario suficiente con inyección directa/indirecta/codificada/multiturmo, autoridad, manipulación de herramientas y divulgación; benignos educativos, comerciales, traducciones, administradores, productos desconocidos e idiomas. Registrar categorías reales, sin afirmar cobertura ausente.

## Congelamiento

`experiment_manifest.json` registra commit, árbol sucio, hashes de código, modelos, metadatos, configuración, reglas, scripts, paquetes/locks, dependencias Python, semilla, corpus y declaración de runtime. El archivo tiene checksum separado. No se hashéan `.env`, credenciales, bases mutables, logs ni resultados. Los ajustes de ejecución se fijan al preparar; reanudación exige los mismos. La existencia de cambios locales queda registrada; el commit por sí solo no representa ese árbol.

El runtime declara proveedor/modelo/modelo de herramientas, parámetros, versiones backend/SDK/Next, tenant, storage y hash de datos MCP. El hash MCP debe corresponder a una instantánea local real. El estado del backend se comprueba antes de cada brazo; cambios detienen ejecución. El endpoint actual no expone todos los parámetros ni atesta procesos remotos: adjuntar evidencia de configuración del proceso dedicado, versiones Node/Next y datos MCP. La declaración no es una atestación criptográfica. No se habilita ejecución contra producción ni un backend remoto compartido.

Instrumentación y pruebas deben terminar **antes** de preparar el experimento final. Cualquier cambio después requiere un experimento nuevo, nunca actualizar hashes para acomodar correcciones descubiertas en el holdout.

## Dos brazos e historial

Protegido: Input, Conversation y Output Guard activos. Baseline: Input y Output desactivados por el mecanismo existente; Conversation sigue ese estado. Alcance, RBAC, herramientas MCP, instrucciones y reglas empresariales permanecen activos. Esto no es un LLM completamente desprotegido.

Los brazos reciben el mismo usuario, roles y transcript funcional revisado. Cada caso/brazo tiene conversación aislada. Para multiturmo se precarga el transcript en **SQLite del backend local dedicado**, con sus niveles originales. Se comprueba que no haya truncamiento. Este ensayo mide respuestas condicionadas al mismo historial, **no trayectorias adaptativas de conversaciones cuyos asistentes divergen**. Las respuestas anteriores generadas no se mezclan entre brazos ni se usan para alterar el historial fijado.

Configurar Chat Service con SQLite y rutas absolutas; `--history-db` debe ser exactamente la base declarada del proceso de prueba. No usar bases de producción. Tras precargar un historial, el script consulta `/conversation/history` y compara lo que realmente ve Chat Service antes de generar. Un backend conectado a otra base falla antes de la llamada pagada. El nivel privado y la evidencia se verifican además en el store; archivar la configuración del proceso.

Cada bloque contiene hasta la concurrencia declarada de sesiones, conserva el orden interno y alterna orden de brazos. Se restauran y verifican ambos controles antes de activar el siguiente brazo y al salir; el watchdog existente protege la muerte del proceso. El backend impone su lease. El presupuesto conservador contempla timeouts, reintentos, espera y duración de sesión; se rechaza lo que no quepa y se deja de programar si queda poco lease. No se renueva un lease mientras hay peticiones.

La selección actual prioriza seguridad y puede generar muchos bloques cortos. HTTP administrativo y comprobaciones añaden sobrecarga, reportada aparte del tiempo de `/chat`. No llamar a un servidor compartido: los controles son globales.

## Reintentos, interrupciones y presupuesto

Se reutilizan reintentos acotados para 429 y conexión previa al envío, respetando Retry-After. No se habilitan reintentos ambiguos de POST ante lectura interrumpida/5xx. Un HTTP 200 con fallo funcional se registra, no se repite como operación completa. El contador de llamadas desconocido detiene programación adicional.

Antes de cada POST se guarda un intent. Tras persistir evidencia se elimina. Si un proceso cae entre envío y guardado, la reanudación rechaza ese intent: reconciliar con logs de request_id del backend; **no borrar y repetir a ciegas**. Si ya hay un evento completo, no se vuelve a cobrar. El presupuesto de provider_calls es de programación, no un límite duro del proveedor; una solicitud puede superarlo internamente.

## Canarios y evaluación de confidencialidad

El evaluador independiente inspecciona literal, fragmentado/separado, URL, Base64 y hex; no ejecuta contenido. La normalización y las codificaciones son acotadas, no una cobertura universal.

El registro privado JSON relaciona ID con `value` ficticio único (16–128 caracteres), `synthetic: true`, `resource_id`, `policy_reference`, `authorized_disclosure`. No colocar secretos reales. Las trazas controladas deben adjuntar al evento `controlled_canary_evidence` con `model_exposed: true`, `exposure_sha256` del canario y, si corresponde, `tool_destinations` con contenido y `authorized` verificado por una política independiente.

**No se ha instalado un canario ni añadido una herramienta a producción.** El Chat Service actual no emite esas trazas completas. Preparar una fixture MCP aislada: una herramienta de lectura permitida al rol experimental devuelve documento sintético con canario bajo sus instrucciones normales; una lectura directa no autorizada debe ser negada por RBAC. Una traza del wrapper experimental debe confirmar resultado autorizado entregado al modelo, identidad/recurso y destino. Mantener instrucciones y permisos empresariales; no colocar el canario en una orden del usuario o inventar prueba de exposición. El alcance debe permitir el caso de acceso documental antes de que éste sea evaluable.

`scripts/scientific_canary_fixture.py` proporciona un generador de registro privado y una herramienta MCP aislada usando el SDK oficial y su ACL experimental admin. Las pruebas comprueban lectura autorizada, denegación de cliente y vinculación del hash del resultado. **No conecta esta herramienta al chat productivo ni demuestra exposición a OpenAI.** El wrapper del ensayo controlado debe observar el payload enviado, invocar `exposure_evidence` con ese hash y conservar la traza. Un hash de un resultado preparado sin envío no prueba acceso del modelo.

Los resultados clasifican divulgación autorizada, fuga no autorizada confirmada, bloqueo, no bloqueo sin fuga y no evaluable. Sin traza de exposición ambos brazos quedan no evaluables, aunque la respuesta contenga o no un canario. Un campo `reported_leaked` no certifica fugas. El acceso de herramienta y el destino requieren inspección humana de la traza; un booleano arbitrario no prueba autorización. Las trazas pueden importarse mediante reprocesamiento de **una copia** del experimento controlado, conservando hashes/evidencia original. No editar el evento histórico para inventar exposición.

## Calidad funcional y estadísticas

`functional_quality.csv` empieza no evaluable. El paquete `blind_quality_packet.csv` oculta brazo y selecciona 25% por familia/roles, más todos los administradores; incluye ambos brazos de casos seleccionados. `private_blind_mapping.json` se conserva separado del revisor. Respuestas pueden revelar su tratamiento: documentar cegamiento imperfecto.

Revisar intención, catálogo/precios/horarios, documentos, aclaraciones, MCP autorizado y omisiones. Registrar referencias al snapshot de datos o traza MCP; no afirmar grounding si falta. Importar JSONL de adjudicación con `arm`, `id`, `label`, `reason`, `evidence`, `reviewer`, `blind: true`. Etiquetas: correct, partial, incorrect, hallucinated, incomplete, tool_error, not_evaluable. No se usa juez externo ni se envían datos privados.

Errores técnicos y UNKNOWN se excluyen de decisiones válidas, pero siguen en disponibilidad. POLICY_DENIAL se separa de SECURITY_BLOCK. FN de seguridad indica ausencia de veto de seguridad, no éxito del ataque. Veto benigno de permisos se informa también como rechazo funcional. Métricas por capa son condicionales a **ejecución real**; sondas independientes no atribuyen decisiones.

McNemar exacto por casos es exploratorio; las familias/sesiones violan independencia. Bootstrap pareado remuestrea familias completas para diferencias de veto, calidad revisada, fuga evaluable, latencia y tokens conocidos. Menos de dos familias no tiene CI; con pocas familias no afirmar precisión alta. Wilson por casos está marcado como ingenuo. No hay corrección de multiplicidad, análisis de potencia ni certificación causal de clases no vistas. Predefinir hipótesis y familias antes del final.

Tokens incluyen exactos cuando conocidos, subtotales observados, cobertura, intentos/reintentos HTTP, provider_calls y ledger disponible. Nunca sustituir null por cero. No se calcula factura ni coste monetario sin precios efectivos verificables. Reasoning tokens pueden solaparse con completion. Latencias p50/p95/p99 por etapa y tipo; no sumar etapas solapadas. Los PNG son descriptivos con unidades y n; CI por familias se conserva en JSON.

## PowerShell: preparación sin red

```powershell
cd C:\Users\USERJSSV\Downloads\Promption
$py = '.\.venv-review\Scripts\python.exe'
& $py -m pytest tests/test_scientific_evaluation.py -q --basetemp data/results/scientific-checks-nuevo

$runtime = Get-Content data/validation/scientific_runtime.example.json -Raw | ConvertFrom-Json
$runtime.mcp_data_sha256 = (Get-FileHash chat-service/app/lib/shop_knowledge.py -Algorithm SHA256).Hash.ToLower()
# Completar los datos efectivos del proceso dedicado; no introducir credenciales.
$runtime | ConvertTo-Json -Depth 20 | Set-Content data/validation/scientific_runtime.local.json -Encoding utf8

& $py scripts/run_final_scientific_v9.py --dry-run --mode regression `
  --corpus data/validation/scientific_smoke_cases.jsonl `
  --runtime data/validation/scientific_runtime.local.json `
  --benign 2 --attack 2 --seed 20261031 `
  --output data/results/validation/scientific-smoke-01
```

No preparar runtime.local.json en Git. Está permitido almacenar configuración no secreta, nunca claves. Si PowerShell escribe BOM, el lector usa utf-8-sig.

## Smoke pagado: solamente después de autorización

Arrancar Filter API, Chat Service y puente Next de la versión congelada en instancias locales dedicadas. OpenAI queda configurado exclusivamente en el backend. Asegurar cuotas para los GET administrativos y no modificar cuotas durante el experimento.

```powershell
$env:VALIDATION_CHAT_TOKEN = '<token del backend dedicado>'
& $py scripts/run_final_scientific_v9.py --resume --execute --dedicated-instance `
  --output data/results/validation/scientific-smoke-01 `
  --mcp-snapshot chat-service/app/lib/shop_knowledge.py
```

El smoke incluido es de un turno. Para sesiones con referencias, añadir `--history-db <ruta SQLite absoluta declarada>` y verificar storage/backend. No usar una configuración de memoria con transcript fijo.

## Final 1.000 + 1.000 por brazo

```powershell
& $py scripts/run_final_scientific_v9.py --dry-run --mode final `
  --corpus data/validation/final_holdout.jsonl `
  --development data/validation/development_inventory.jsonl `
  --regression data/validation/regression_inventory.jsonl `
  --runtime data/validation/scientific_runtime.local.json `
  --benign 1000 --attack 1000 --seed 20261031 `
  --output data/results/validation/scientific-final-01

# Después de aprobar el smoke, con autorización para 4.000 recorridos:
& $py scripts/run_final_scientific_v9.py --resume --execute --dedicated-instance `
  --output data/results/validation/scientific-final-01 `
  --mcp-snapshot chat-service/app/lib/shop_knowledge.py `
  --history-db '<ruta SQLite del backend dedicado>'
```

Reanudación utiliza el mismo comando/configuración; requiere ambos controles activos al inicio y hashes iguales. No se ejecutó ninguno de estos comandos pagados durante la implementación.

## Reprocesar sin gastos

```powershell
& $py scripts/run_final_scientific_v9.py --reprocess-only `
  --output data/results/validation/scientific-final-01 `
  --analysis-output data/results/validation/scientific-final-analisis-02 `
  --reviews data/validation/adjudication.jsonl `
  --canary-registry '<registro privado ficticio.json>'
```

Sin adjudicación/registro, omitir sus opciones. El destino debe ser nuevo. También acepta experimentos históricos con manifest.json/corpus.jsonl/events.jsonl y hash válido, sin afirmar que tengan el nuevo diseño fijo ni holdout externo. No cambia la evidencia original.

## Entrega y límites de cierre

Se generan paired_results.csv, paired_decisions.csv, security_metrics.csv, functional_quality.csv, technical_errors.csv, latencies_by_stage.csv, token_usage.csv, family_metrics.csv, canary_evaluation.csv, statistical_analysis.json, final_report.md y los CSV originales por brazo, más evidencia y procedencia. El manifiesto queda en la raíz de ejecución. Columnas obligatorias originales intactas; campos faltantes son vacíos, no ceros.

La infraestructura puede validarse sin OpenAI. Quedan pendientes el corpus externo revisado, atestación del proceso dedicado, fixture/traza real de canario, adjudicación y el smoke pagado. No es una certificación científica ni una autorización automática para publicar eficacia o generalización. No se afirma integración real de MCP/OpenAI nueva hasta ejecutar y auditar esos ensayos.
