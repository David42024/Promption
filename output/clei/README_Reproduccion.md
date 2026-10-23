# Reproducción del estudio de Promption para CLEI

Este paquete local acompaña el manuscrito de 15 páginas. Contiene el código necesario para repetir los ocho entrenamientos, los datos procesados utilizados y los resultados originales. No es un depósito público y aún no tiene un identificador persistente.

## Contenido

La estructura de carpetas se conserva para que el evaluador encuentre la raíz del proyecto. `output/clei/evidence/manifest.json` registra el commit evaluado, las versiones, las huellas SHA-256 de las entradas y el alcance de las mediciones. `metrics.csv` contiene 32 filas, una por combinación de experimento y política. `predictions.csv` permite recalcular las matrices de confusión. `corpus_manifest.csv` contiene los 5.872 identificadores únicos.

Los archivos originales de reglas, configuración, código y datos no se modificaron para elaborar el artículo. El evaluador nuevo importa esas funciones y ajusta modelos en memoria. El modelo previamente serializado se conserva por trazabilidad, pero no se utiliza para las predicciones nuevas del artículo. La configuración contiene direcciones públicas y parámetros; no se incluyen credenciales, archivos de entorno ni el historial Git.

El paquete incluye código de la biblioteca y una selección de pruebas para consulta. No incluye la aplicación completa ni sustituye el repositorio para verificar dashboard, API o todos los adaptadores. Las comprobaciones operativas originales y sus límites están documentados en `Cumplimiento_CLEI.md` y en los registros de evidencia.

## Ejecución

1. Extraer el ZIP en una carpeta nueva y conservar su estructura.
2. Preparar un entorno Python 3.11.15 con las versiones registradas en `output/clei/evidence/environment_packages.json`. Para el experimento principal bastan las dependencias de `requirements-reproduction.txt`; el paquete incluye las versiones exactas de las dependencias científicas usadas. El archivo de versiones no constituye una imagen completa del sistema operativo ni de sus bibliotecas numéricas.
3. Comparar las huellas de las entradas con `output/clei/evidence/manifest.json` antes de ejecutar. Conservar una copia de la evidencia original porque la ejecución reemplaza los resultados dentro de la carpeta extraída.
4. Desde la raíz extraída, ejecutar:

```bash
python output/clei/evidence/evaluate_article.py > output/clei/evidence/reproduction.log 2>&1
```

El experimento no requiere un servicio LLM ni acceso a sus API. Entrena tres particiones aleatorias y cinco particiones que excluyen una fuente completa. Las reglas y umbrales permanecen fijos. En una extracción sin Git, el evaluador conserva el identificador del commit registrado en el manifiesto original. Las últimas adaptaciones del evaluador amplían las huellas y permiten esa extracción; no alteran el protocolo de entrenamiento o las decisiones.

## Comprobación de resultados

Verificar 5.872 entradas, ocho experimentos, cuatro políticas por experimento y 9.397 filas de predicción. En `random_42`, la política `three_state` debe tener TP 445, FP 52, FN 89 y TN 589. Sus decisiones deben sumar 497 BLOCKED, 678 GUARDED y 0 ALLOWED. Los tiempos son específicos del equipo y no deben coincidir exactamente. Cambios de bibliotecas pueden afectar probabilidades próximas a los umbrales.

El contenido de los prompts es material de investigación. Las métricas miden clasificación y derivación; no prueban compromiso de un modelo ni eficacia del control posterior. La disponibilidad local del corpus tampoco certifica una licencia común para todas las colecciones originales; las fuentes están citadas en el artículo para revisar sus condiciones antes de publicar el paquete.
