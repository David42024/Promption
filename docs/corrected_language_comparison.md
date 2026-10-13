# Comparación de idiomas con datos corregidos

```powershell
.\.venv-review\Scripts\python.exe scripts/compare_corrected_training.py --execute --activate --cases 200
```

Sin `--execute` no entrena ni cambia artefactos. Sin `--activate` conserva los
modelos candidatos separados del modelo activo. La selección compara español,
inglés y ambos, con TF-IDF de palabras y caracteres más regresión logística y
el mismo umbral de 0,66. Solo `prompt` se utiliza como variable predictora.

La comparación utiliza el archivo bilingüe de `data/processed/archivos_validos`.
Los modelos monolingües reciben exclusivamente las filas de entrenamiento de
su idioma. Todos se evalúan con las mismas particiones bilingües. Los enlaces
de traducción y los identificadores de familia, grupo y split se unen antes
de separar los datos. Si un componente cruza particiones, se reserva completo
en la partición más restrictiva: external, test, validación, entrenamiento.

El ganador se elige por F1 medio entre idiomas en los originales de validación;
las plantillas de validación solo desempatan. La prueba no determina la selección.
Se informan resultados separados por idioma y por originales frente a sintéticos.
Los valores no son directamente comparables con el corpus anterior, pues cambiaron
etiquetas, familias y composición.

El benchmark usa el mismo `BenchmarkRunner` anterior sobre 200 casos españoles
de test, 100 benignos y 100 ataques seleccionados con semilla 42. Genera las
columnas habituales, evidencia de errores y métricas por capa. Es una prueba
local sin LLM: no mide filtraciones reales, alcance, MCP ni Output Guard y no
consume tokens. Las variantes sintéticas pueden elevar las métricas y la
revisión por reglas no sustituye la revisión humana para una publicación.

La activación guarda una copia de los modelos, configuraciones y datos previos.
`paths.reviewed_dataset` configura el dataset corregido como fuente autorizada:
las correcciones y cuarentenas del corpus antiguo no se vuelven a aplicar.
Las futuras particiones respetan `partition_scheme=reviewed_connected_v1`.
Los servicios en ejecución deben reiniciarse para cargar el modelo nuevo.

Para la prueba final de 1.000 casos, con el idioma de entrenamiento ya elegido:

```powershell
.\.venv-review\Scripts\python.exe scripts/compare_corrected_training.py --execute --activate --training-mode bilingual --benchmark-language all --reserve-test --cases 1000 --seed 42
```

El archivo original solo reservaba 845 filas de test. `--reserve-test` mueve
familias completas desde entrenamiento hasta disponer de al menos 500 filas
por clase; nunca utiliza validación para completar la muestra. Esto sucede
antes de entrenar desde cero. Después selecciona sin reemplazo 500 benignos
y 500 ataques de test. Los resultados previos no eligen el candidato usando
estos nuevos casos. `--benchmark-language es` limita la muestra a español,
y `en` a inglés, manteniendo las familias bilingües en una sola partición.
