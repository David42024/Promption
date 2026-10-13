# Entrenamiento multilingüe para la VPS

El backend pesado mantiene el encoder preentrenado `intfloat/multilingual-e5-small` y reentrena su clasificador Random Forest. No realiza fine-tuning del encoder ni del LLM de OpenAI. Se fija la revisión del encoder en configuración para reproducir los mismos embeddings en entrenamiento y producción.

## Datos y separación

`promption/training/spanish_corpus.py` contiene 40 semillas maliciosas y 40 legítimas redactadas en español. Cada semilla genera 12 contextos, incluidos fichas, correos, tickets y resultados de herramienta: 960 variantes sintéticas. Son 80 familias, no 960 observaciones independientes. Las familias nuevas pertenecen exclusivamente a entrenamiento. Ningún texto o familia anterior cambia de partición.

Las etiquetas distinguen instrucciones de anulación/extracción de consultas conceptuales y comerciales legítimas. No equivalen a permisos de negocio: los controles por rol continúan en la aplicación. El corpus no contiene credenciales reales.

## Reproducción

Instalar las dependencias de `.[embeddings,reports]` en el entorno del proyecto. Para CPU, instalar primero PyTorch desde su índice de wheels CPU. La API Docker también instala el extra embeddings y PyTorch CPU.

```powershell
.\.venv-review\Scripts\python.exe scripts/retrain_spanish_model.py --execute --activate
```

El script está diseñado para aplicar v1 una sola vez. Conserva modelo, configuración, manifiesto y dataset anteriores en un backup. Primero genera un candidato en `data/results/spanish-retrain-*`, sin modificar el modelo activo. Sus comprobaciones de activación usan únicamente validación: recall general y español no inferiores al baseline y FPR general como máximo dos puntos porcentuales por encima del baseline. Si no cumple, conserva el candidato y devuelve código 2 sin activarlo.

`--resume-output <directorio> --tune-validation` permite retomar el candidato y probar hasta cinco configuraciones del bosque, reutilizando los embeddings verificados. La búsqueda recibe únicamente entrenamiento y ventanas de validación; no selecciona parámetros con test o external. Registra cada intento en `validation_tuning.json`. Una mejora de recall que exceda el límite de falsos positivos se rechaza.

La comparación aplica las ventanas de `MLFilter.analyze` y el máximo de sus scores. Las métricas de texto completo quedan identificadas por separado. El umbral se conserva en 0,66. No se utiliza el test o external para seleccionar hiperparámetros.

La baseline es el modelo ligero existente; cambian tanto el backend como sus datos de entrenamiento. Los resultados no permiten atribuir toda mejora exclusivamente al español. Las etiquetas de idioma antiguas provienen del detector léxico existente; las nuevas tienen idioma español declarado.

## Despliegue

Subir juntos los siguientes artefactos y fuentes:

- `models/random_forest.pkl` y `models/random_forest.metadata.json`.
- `config/config.yaml` y `promption/resources/config.yaml`, con `use_lightweight_ml: false` si pasó la validación.
- `data/processed/split_manifest.json`, `data/raw/spanish_augmentation.csv` y el código de entrenamiento actualizado.
- `requirements-api.txt`, `Dockerfile` y `.dockerignore` actualizados para el encoder.

La VPS necesita acceso al repositorio público del encoder en el primer arranque o una caché preinstalada de la revisión fijada. Reiniciar los workers de la Filter API: una instancia ya cargada no cambia de backend sólo por reemplazar archivos. Empezar con un worker y medir RAM, CPU y latencia bajo la concurrencia real; cada proceso carga su propio encoder.

La imagen instala PyTorch CPU y fija `sentence-transformers` y `transformers` a las versiones usadas para validar el artefacto. El clasificador depende también de la versión de scikit-learn indicada en sus metadatos. No es necesario subir los caches locales de embeddings ni los backups.

Para varios procesos, enviar logs a stdout o asignar un archivo por proceso mediante configuración. El `RotatingFileHandler` existente no coordina la rotación entre procesos; durante las pruebas locales con servicios ya abiertos produjo errores de archivo ocupado en Windows. Esto no es un fallo del clasificador, pero puede afectar el registro y la latencia.

Comprobar `/api/v1/health`, realizar una solicitud de calentamiento al filtro y comprobar en una entrada incierta que el ML se ejecuta y está `HEALTHY`. El Chat Service debe apuntar a la Filter API de la VPS. Esta preparación local no despliega ni certifica Incubunt.

## Resultado del 10 de octubre de 2026

El candidato de esta ejecución **no se activó y no se recomienda para producción**. El modelo ligero y su manifiesto oficiales siguen intactos. El bosque reentrenado está en `data/results/spanish-retrain-20261010-061400-f0ae56/random_forest.pkl`, con metadatos, corpus, manifiesto y comparación en esa misma carpeta.

Se entrenó con 4.054 filas, de las que 1.098 son españolas, dentro de un corpus total de 8.783 filas. Se mantuvieron 658 filas de validación, 661 de test y 3.410 externas. Las métricas siguientes corresponden al ML aislado, con la agregación de ventanas usada en producción y umbral 0,66; no son ASR con LLM real.

| Conjunto | Ligero: recall | Pesado: recall | Ligero: FPR | Pesado: FPR |
| --- | ---: | ---: | ---: | ---: |
| Validación general | 75,92 % | 66,22 % | 3,90 % | 4,74 % |
| Test general | 79,47 % | 72,85 % | 5,29 % | 8,36 % |
| External español | 43,41 % | 46,82 % | 3,02 % | 2,14 % |

El external español contiene 645 ataques y 562 entradas legítimas. El test español sólo contiene 20 ataques y 7 entradas legítimas; sus porcentajes tienen poca estabilidad. La mejora externa española no compensa la regresión general. Ninguna de las cinco configuraciones adicionales cumplió los criterios de validación: las que elevaron el recall también aumentaron demasiado los falsos positivos.

La regresión local de 20 mensajes dejó cuatro de seis ataques bloqueados por el filtro de entrada y dos en `GUARDED`; ninguno de los catorce benignos fue bloqueado por ese filtro. Son casos que ya informaron los temas del entrenamiento, no una evaluación independiente. No se ejecutaron alcance, permisos, MCP ni generación LLM en esa regresión.

Antes de sustituir el modelo activo conviene ampliar familias españolas anotadas y negativos difíciles, y evaluar un entrenamiento coherente con las ventanas de inferencia. Actualmente el bosque aprende embeddings de textos completos, mientras producción agrega el máximo de fragmentos: esa diferencia puede aumentar los falsos positivos. La elección del modelo y del umbral debe seguir usando validación; futuras mejoras necesitan además un nuevo conjunto de evaluación independiente.
