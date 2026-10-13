# Modelo ligero con entrenamiento ampliado en español

Se mantiene TF-IDF de palabras y caracteres con LogisticRegression. No se cambian
proveedor de chat, modelo LLM, umbral de decisión (0,66), heurísticas ni permisos.
Las dependencias añadidas exclusivamente para desplegar el encoder pesado se retiraron.

## Datos y aislamiento

- 1.000 originales ingleses seleccionados de entrenamiento: 500 ataques y 500 benignos.
- Selección reproducible, semilla 42, con diversidad de fuentes públicas y textos de hasta
  1.500 caracteres. Excluye correos, posibles credenciales y fuentes privadas.
- OpenAI `gpt-5.4-nano` produjo 997 traducciones no vacías ni idénticas al original.
- Se eliminaron cuatro coincidencias con textos existentes y dos traducciones duplicadas.
- Se incorporaron **991 traducciones**: 495 ataques y 496 benignas, de 991 familias originales.
- Se añadieron 80 ejemplos propios en español, 40 ataques y 40 benignos. Se utiliza
  una variante por familia, sin contar envoltorios equivalentes como ejemplos independientes.
- Entrenamiento: 4.165 filas, incluyendo 1.209 en español, frente a las 138 anteriores.
- Validación: 658 filas; test: 661; external: 3.410. Todas las familias originales
  conservan su partición. Ninguna traducción de val/test/external entra en entrenamiento.

Cada traducción conserva `family_id`, `group_id`, etiqueta, SHA-256 del original,
fuente original y modelo traductor. Los textos adversarios se envían como datos
para traducir, con instrucciones de no obedecerlos y salida JSON estructurada.
La revisión de muestras confirma traducciones en español; el detector de idioma
del repositorio puede clasificar textos españoles cortos como ingleses, por lo que
se conserva el idioma declarado del proceso de traducción.

## Resultados del ML al umbral real

| Partición | Recall anterior | Recall nuevo | FPR anterior | FPR nuevo |
|---|---:|---:|---:|---:|
| Validación general, 299 ataques / 359 benignos | 75,92 % | 76,25 % | 3,90 % | 3,62 % |
| Test general, 302 ataques / 359 benignos | 79,47 % | 79,80 % | 5,29 % | 5,01 % |
| External español, 645 ataques / 562 benignos | 43,41 % | 78,76 % | 3,02 % | 4,45 % |
| Test español, 20 ataques / 7 benignos | 75,00 % | 65,00 % | 28,57 % | 28,57 % |

La activación se decide exclusivamente con validación: recall general y español
no inferiores al anterior, FPR general con tolerancia máxima de un punto porcentual
y FPR español sin aumento. Los cuatro controles se cumplieron. El test español
pequeño empeora en dos ataques; no se ajustan parámetros utilizando ese test.
La mejora externa no representa una certificación general de seguridad.
Estas métricas describen el clasificador ML; un benchmark sin LLM mide un proxy,
no extracción real de secretos. Chat, alcance, MCP y Output Guard requieren su
validación de extremo a extremo después del despliegue.

## Archivos y reproducción

- `promption/training/spanish_translation.py`: selección, procedencia y limpieza.
- `scripts/translate_training_spanish.py`: traducción con checkpoint, límites,
  concurrencia acotada, parada ante errores de configuración/cuota y métricas de uso.
- `scripts/retrain_lightweight_spanish.py`: entrenamiento aislado, comparación y
  activación condicional con copia de seguridad.
- `data/raw/spanish_translations.csv`: traducciones incorporadas.
- `data/raw/spanish_augmentation.csv`: 80 ejemplos propios incorporados.
- `models/lightweight_classifier.pkl` y `.metadata.json`: artefacto activo y procedencia.
- `data/processed/split_manifest.json`: manifiesto vinculado al modelo.
- `tests/test_spanish_translation.py`: procedencia, etiquetas, aislamiento, limpieza,
  errores del proveedor y controles de activación.

Preparación sin llamadas externas, desde PowerShell:

```powershell
.\.venv-review\Scripts\python.exe scripts/translate_training_spanish.py --limit 1000 --out data/results/translation-next/spanish.csv
```

Para traducir, configurar `OPENAI_API_KEY` y `OPENAI_MODEL` en el entorno sin
versionar secretos y añadir `--execute`. El script no recupera credenciales de
otros procesos; durante esta ejecución se reutilizaron en memoria las credenciales
autorizadas del servicio local. El límite `--max-calls` incluye intentos anteriores
registrados en el checkpoint; no se reintentan llamadas automáticamente.

El corpus v1 ya está incorporado. Volver a activar la misma ampliación se rechaza
por solapamiento; una ampliación siguiente debe utilizar nuevos originales/familias
y compararse con el modelo entonces activo.

## Evidencias y despliegue

Las evidencias están en `data/results/spanish-light-20261010/`: checkpoint,
`translation_cleanup.json`, `candidate/comparison.json`, metadatos y benchmark
aislado. Las llamadas iniciales rechazadas por un parámetro incompatible y el lote
piloto también se conservaron: no se presenta la ejecución completa como libre
de errores. Uso observado: 226.635 tokens. El total global permanece desconocido
porque los rechazos HTTP no proporcionan métricas; `known_usage` conserva el subtotal.

Para desplegar, incluir el modelo, sus metadatos, el manifiesto y ambos CSV nuevos,
manteniendo `use_lightweight_ml: true`. `training_data.csv` es un archivo generado
ignorado por Git y puede reconstruirse desde los CSV y los archivos de overrides,
cuarentena y vínculos de traducción. No enviar únicamente el `.pkl` con un manifiesto
antiguo. Reiniciar los servicios para recargar el singleton ML; este trabajo no
modifica automáticamente la VPS ni los procesos locales que ya tenían el modelo cargado.

El log rotativo local compartido por varios procesos produce `WinError 32` en Windows.
Para estas comprobaciones se utilizó una configuración equivalente con archivo de
log aislado; no se relajaron las aserciones de rendimiento.
