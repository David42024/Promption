# Experimento real emparejado con OpenAI

`scripts/run_real_paired_benchmark.py` genera por defecto 5.000 mensajes distintos y los evalúa en dos brazos: sin protección y Filter API → OpenAI → Output Guard. Son 10.000 evaluaciones por entorno; los bloqueos previos evitan llamadas al proveedor. No ejecuta consultas sin `--execute`. No utiliza respuestas simuladas.

Distribución configurable: 2.500 benignos, 2.000 ataques y 500 casos de permisos/alcance. Son variantes de 45 familias sintéticas: **no equivalen a 5.000 observaciones independientes ni a un holdout de fuentes**. Antes del artículo, revisar etiquetas y publicar la distribución por familia. Los casos de permisos no certifican RBAC: este experimento no ejecuta MCP ni las políticas del chat completo.

Ambos brazos reciben el mismo sistema, contexto y modelo explícito. Se usa exclusivamente una clave ficticia como canario. El ASR mide su divulgación literal entre ataques con ambos resultados válidos. No detecta toda posible divulgación transformada ni certifica confidencialidad general. Las matrices por capa miden bloqueo, distinto de fuga; ML omitido aparece como no evaluado. Errores y salidas truncadas se excluyen del ASR y se contabilizan aparte. Tokens desconocidos permanecen nulos y se publican subtotales conocidos.

Las llamadas OpenAI se originan en la máquina del script. Cambiar la URL del filtro compara el núcleo local y remoto, **no la latencia del backend completo en Incubunt**. Para el recorrido completo protegido con MCP y alcance, conservar `compare_llm_environments.py`; no hay un bypass seguro del chat de producción en este script.

## Preparación sin red

```powershell
.\.venv-review\Scripts\python.exe -m pytest tests/test_real_paired_benchmark.py -q
.\.venv-review\Scripts\python.exe scripts/run_real_paired_benchmark.py --model "MODELO_CONFIGURADO" --dry-run --write-corpus data/validation/paper_cases_5000.jsonl
```

El archivo de corpus no se sobrescribe. Credenciales únicamente en `OPENAI_API_KEY` y `VALIDATION_FILTER_KEY`, correspondientes al entorno. No se guardan claves. La URL debe apuntar a una Filter API real con `/filter` y `/output-guard`; no asumir que la URL de la tienda expone esos endpoints.

## Piloto y ejecución completa

```powershell
.\.venv-review\Scripts\python.exe scripts/run_real_paired_benchmark.py --model "MODELO_CONFIGURADO" --filter-url http://127.0.0.1:8000/api/v1 --execute --limit 20 --max-provider-calls 40 --output data/results/validation/paper-local
```

Para completar ese mismo experimento, repetir los parámetros con `--resume data/results/validation/paper-local`, quitar `--output` y `--limit`, y poner `--max-provider-calls 10000`. El presupuesto es acumulativo e incluye intentos fallidos. La reanudación exige idéntico corpus, modelo, sistema, URL y límite de tokens.

Para Incubunt, utilizar su URL verificada de Filter API y una carpeta nueva, manteniendo semilla, modelo y proporciones. Cambiar proporciones con `--benign`, `--attack`, `--policy`; la suma determina el número de pares.

Se ejecuta secuencialmente, sin reintentos automáticos. Hace dos sondas del filtro sin LLM antes de iniciar. Detiene la programación ante 401, 403 o 429. `arms.jsonl` persiste cada brazo con fsync; `evidence.jsonl` guarda pares; `benchmark.csv` conserva las 21 columnas obligatorias; `summary.json` incluye ASR comparable, FP/FN, errores, tokens y percentiles de latencia. Exporta cada 50 pares y al finalizar. Si el proceso muere entre enviar la petición y guardar el checkpoint, no existe garantía de exactamente una llamada: comprobar el uso del proveedor antes de reanudar. No compartir la misma carpeta entre procesos.

Estimación orientativa: 10–24 horas por entorno con ejecución secuencial y pausa de 2 segundos, según latencia, proporción de bloqueos y tokens de razonamiento. Medir el piloto y extrapolar; no es un tiempo garantizado. Dos entornos duplican el volumen. `--max-tokens 512` puede truncar respuestas de modelos con razonamiento: evaluar el piloto antes de fijar ese parámetro para todo el experimento.

El antiguo `run_academic_benchmark.py` genera resultados aleatorios: sus cifras no deben presentarse como evidencia de llamadas reales en el artículo.
