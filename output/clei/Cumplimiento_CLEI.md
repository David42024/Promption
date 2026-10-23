# Verificación del artículo para CLEI Electronic Journal

Revisión actualizada del 2 de octubre de 2026. Se contrastó Checklist_CLEI.docx con las cinco páginas de AuthorInstructions2016-OTH.pdf, que el usuario identifica como las reglas vigentes, y con el portal de la revista. El PDF de instrucciones se utiliza como autoridad para el formato. La checklist se utiliza como lista de aspectos que revisar, no como una plantilla de la revista cubana.

El artículo presenta investigación empírica nueva sobre Promption. Contiene ocho entrenamientos ejecutados, comparación de cuatro políticas, evaluación por fuente y una auditoría del procedimiento anterior. La redacción y los resultados se prepararon para este trabajo. Según la declaración del usuario, el software y sus resultados no se han publicado ni enviado previamente.

| Punto de la checklist adjunta | Estado del manuscrito | Evidencia |
|---|---|---|
| 1 Afiliaciones y correspondencia | Datos incorporados; contacto provisional | Primera página: ambos autores, Universidad Nacional de Trujillo, Trujillo, Perú, correos y ORCID. Roberto figura como contacto provisional en los metadatos |
| 2 DOI propio y rótulo Temática | No se añadieron | Se incluyen DOI o enlaces en las 14 referencias |
| 3 Letra del cuerpo | Conforme | Times New Roman 10 puntos, una columna e interlineado sencillo |
| 4 Título | Conforme | Centrado, negrita, 16 puntos, sin línea decorativa |
| 5 Jerarquía de encabezados | Conforme | Secciones numeradas a 12 puntos; subsecciones a 10 puntos; sin mayúsculas sostenidas |
| 6 Organización del artículo | Adaptada al estudio | Introducción, trabajos relacionados, sistema, método, resultados, discusión, validez y conclusiones |
| 7 Conclusiones | Verificado | Conclusiones sin subtítulos vacíos ni evidencia nueva |
| 8 Residuos y encabezados vacíos | Verificado | Revisión visual de todas las páginas y comprobación estructural |
| 9 Palabras clave | Conforme | Cinco términos pertinentes en inglés |
| 10 Leyendas | Conforme | Nueve tablas y tres figuras: numeración consecutiva, dos puntos y sin punto final; tablas sin líneas verticales |

Comprobaciones adicionales: PDF de 15 páginas A4; márgenes superior y derecho de 2 cm, inferior e izquierdo de 2,5 cm; resumen de 182 palabras en la primera página; paginación en todas las páginas; bibliografía numerada según orden de cita, con enlaces activos. El texto principal está en inglés. Las tablas y figuras están integradas en el texto.

## Verificación contra las instrucciones adjuntas

| Sección del PDF de instrucciones | Requisito | Aplicación en el artículo |
|---|---|---|
| 2, página 1 | Al menos 12 páginas, A4 y márgenes prescritos | 15 páginas, 210 × 297 mm; 2 cm arriba y a la derecha, 2,5 cm abajo y a la izquierda |
| 2, página 1 | Número en cada página y ningún otro encabezado o pie antes de aceptación | Paginación centrada en todas las páginas; sin encabezado editorial |
| 3 y 3.1, página 1 | Times de 10 puntos; título de 16 en negrita; nombres de 12 en negrita; afiliación y correo de 12; bloque centrado | Aplicado; se añadió «and» entre los autores, como en el ejemplo, y se uniformó el tamaño de los ORCID a 12 puntos |
| 3.2 y 3.3, página 2 | Resumen de hasta 200 palabras y palabras clave en primera página, justificados; una columna | Resumen de 182 palabras con sangría simétrica como en el ejemplo; cinco palabras clave separadas por comas; una columna |
| 3.4, página 2 | Referencias IEEE en orden de cita; títulos entre comillas, nombres de publicaciones en cursiva, DOI e hipervínculos | 14 entradas con numeración y enlaces activos; DOI de los siete preprints y URL de conjuntos de datos y documentación. No se inventaron DOI para esas páginas |
| 4, 4.1 y 4.1.1, páginas 2–3 | Secciones de 12 puntos en negrita; subsecciones de 10 en negrita; subsubsecciones de 10 en cursiva; alineación izquierda | Alineación izquierda explícita y estilos aplicados; resumen y referencias sin numeración; no hay subsubsecciones en esta versión |
| 5, página 3 | Figuras insertadas en el texto, numeradas y citadas; leyenda debajo; tablas con leyenda centrada encima, sin líneas verticales ni exceso de ancho; sin punto final en leyendas | Tres figuras citadas como Fig. 1–3 y nueve tablas; leyendas emparejadas con sus objetos; tablas dentro del ancho útil de 16,5 cm |
| 6, página 3 | Inglés comprensible para lectores internacionales y explicación de términos y siglas | Texto en inglés; se completaron las explicaciones de SDK, AI, SHA-256 y CPU; los términos metodológicos se definen en el cuerpo |
| 7, página 3 | Entrega exclusivamente en PDF y comprobación en un visor; no enviar resúmenes extendidos | Artículo completo en PDF; Word se entrega para edición. Se volvió a revisar visualmente la versión completa; el documento aún no se envió |
| Apéndice, página 5 | Indicar nombre y correo del contacto en el mensaje de envío | Metadatos con Roberto Enrique Quezada-Rodríguez y requezadaro@unitru.edu.pe como contacto provisional; deben confirmarse antes del envío |

Los cambios de esta revisión son editoriales y de presentación. Los ocho experimentos, las 32 combinaciones de política y experimento y las 9.397 predicciones permanecen iguales. El encabezado con volumen, número y artículo que aparece en la muestra corresponde a la versión aceptada: la propia sección 2 indica que no se debe añadir al manuscrito de evaluación.

## Evidencia científica

Se evaluaron 5.872 textos únicos de cinco fuentes. El clasificador se ajustó exclusivamente con cada partición de entrenamiento. Los resultados no se presentan como éxito real de ataques contra un LLM: se distingue entre bloqueo de entrada, derivación a protección de salida y compromiso posterior. Los datos históricos no se mezclaron con las mediciones nuevas.

El software original conserva su estado. La auditoría encontró diferencias entre documentación y configuración activa, una política de tres estados en lugar de OR estricto y un error de posiciones en el divisor existente. El procedimiento del artículo evita ese divisor sin modificar el código de producción. Las reglas fijas pudieron conocer las fuentes durante el desarrollo: esta limitación está explicada.

## Comprobaciones operativas

- Pruebas del detector: 80 aprobadas en 11,25 segundos.
- Paquete JavaScript: los cuatro archivos de pruebas aprobaron.
- Benchmark de integración sin LLM: 7.823 filas y las 21 columnas requeridas; guardado en evidencia, sin reemplazar resultados anteriores.
- Inicio del dashboard mediante AppTest: aprobado.
- API: importación, llamada directa de salud y existencia de la ruta en el esquema verificadas. La prueba HTTP mediante TestClient agotó 25 segundos; no se certifica GET 200.
- Suite Python completa: iniciada e interrumpida tras quedar sin progreso. Una ejecución ampliada también agotó su límite; no se declara que las 508 pruebas hayan aprobado.

## Datos que los autores deben cerrar antes del envío

1. Revisar y aprobar ambos la interpretación, referencias y versión final; confirmar contribuciones de autoría, financiación y conflictos de intereses.
2. Confirmar el autor de correspondencia. Se ha propuesto a Roberto provisionalmente.
3. Confirmar el correo de David: se conservó exactamente el mismo correo que el usuario proporcionó para ambos autores.
4. Decidir dónde archivar públicamente el material de reproducción y añadir su enlace persistente si se publica. El paquete local aún no tiene DOI propio.

Se incluyó una declaración transparente de asistencia de IA. No se inventaron declaraciones de financiación, ausencia de conflictos ni aprobación de los autores. No se realizó envío a la revista ni se certifica una evaluación antiplagio institucional. Esta verificación comprueba preparación formal y trazabilidad, no anticipa la decisión editorial.

## Fuentes oficiales revisadas

- [Instrucciones vigentes adjuntas por el usuario](evidence/AuthorInstructions2016-OTH.pdf), cinco páginas, revisadas íntegramente. Se conserva una copia en el paquete de evidencia
- [Directrices y checklist de envío vigente](https://www.clei.org/cleiej/index.php/cleiej/about/submissions)
- [Instrucciones para autores enlazadas desde el portal vigente](https://www.clei.org/cleiej/index.php/cleiej/libraryFiles/downloadPublic/2), documento fechado en 2016
- [Ética y código de conducta](https://www.clei.org/cleiej/index.php/cleiej/Conduct)
- [Proceso editorial](https://www.clei.org/cleiej/index.php/cleiej/EditorialProcess)
- [Página institucional indicada por el usuario](https://clei.org/clei-electronic-journal/)
