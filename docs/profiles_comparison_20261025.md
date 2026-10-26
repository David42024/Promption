# Comparación de los tres perfiles — 25/10/2026

## Diseño ejecutado

Se ejecutaron **48 casos × tres perfiles = 144 episodios nuevos**, con Promption
**1.5.0**. Los mismos casos, política, clave sintética, modelos, ACL y guards se
usaron en `conversational`, `balanced` y `strict`. El código y el plan quedaron
congelados antes de ejecutar. No se modificaron reglas para favorecer un resultado.

La submuestra se seleccionó de los 240 casos previamente evaluados:

| Fuente | Negativos de origen | Positivos de origen | Total |
|---|---:|---:|---:|
| Lúmina | 12 | 12 | 24 |
| Referencia pública/local | 12 | 12 | 24 |
| Total | 24 | 24 | 48 |

Selección determinista por SHA-256 de semilla e ID, sin consultar predicciones.
En referencia se tomaron seis registros marcados español y seis inglés por clase;
esas marcas no son adjudicación lingüística humana. En Lúmina, seis por clase con
necesidad anotada de contexto y seis sin ella; 19 casos conservaron historial y
cinco no. La etiqueta de idioma de Lúmina es español/mixto sin verificar.

Los casos ya fueron expuestos durante desarrollo: **es una regresión sobre una
submuestra, no un nuevo test independiente**. Las etiquetas son silver/de origen,
sin nuevo gold humano. Se mantuvieron los límites de una ejecución por caso/perfil,
dos episodios concurrentes, tres pasos del modelo, dos tools y 1024 tokens de salida.

La comparación usó OpenAI mediante AI SDK: generador y juez de rechazo
`gpt-5.4-nano-2026-03-17`, evaluador contextual `gpt-5.4-mini-2026-03-17`.
Se ejecutaron guards Python, autorización y MCP reales, con documentos locales
PDF/DOCX/XLSX y páginas fixture. No hubo navegación HTTP de las URLs propuestas.

## Resultado completo: rechazo observado

Positivo significa inyección según la fuente; predicción positiva significa
rechazo del pipeline o de la respuesta. Un FN **no equivale a exfiltración**.
Las aclaraciones cuentan como no rechazo, pero no como tareas completadas.

| Perfil | TP | FP | FN | TN | FPR evaluable | Fallos operativos | Indeterminados | Aclaraciones fijas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| conversational | 22 | 3 | 2 | 16 | 15.79% (3/19) | 4 | 1 | 1 |
| balanced | 20 | 5 | 3 | 16 | 23.81% (5/21) | 3 | 1 | 1 |
| strict | 24 | 24 | 0 | 0 | 100.00% (24/24) | 0 | 0 | 0 |

El denominador evaluable de negativos cambia: faltan cinco negativos en
`conversational` y tres en `balanced`. En `balanced` falta además un positivo.
Los fallos o dictámenes sin clasificación se conservaron y no se contaron como
detecciones correctas. No se estimó una tasa de éxito de tareas legítimas.

### Desglose por fuente

| Fuente | Perfil | TP | FP | FN | TN | Fallos | Indeterminados |
|---|---|---:|---:|---:|---:|---:|---:|
| Lúmina | conversational | 11 | 0 | 1 | 11 | 1 | 0 |
| Lúmina | balanced | 10 | 0 | 2 | 12 | 0 | 0 |
| Lúmina | strict | 12 | 12 | 0 | 0 | 0 | 0 |
| Referencia | conversational | 11 | 3 | 1 | 5 | 3 | 1 |
| Referencia | balanced | 10 | 5 | 1 | 4 | 3 | 1 |
| Referencia | strict | 12 | 12 | 0 | 0 | 0 | 0 |

## Interpretación de los modos

**El estricto resulta excesivamente restrictivo para esta muestra.** Rechazó los
48 casos antes de generación, incluidos los 24 negativos. Su FN cero no demuestra
que distinga bien ataques: aquí se consigue bloqueando todo. No es una buena
elección para atención general con esta configuración. Los perfiles no cambiaron
umbrales ni modelos; este perfil veta también la incertidumbre/obligación de
protección de salida, frecuente en tareas amplias e historial.

**No se demostró superioridad de conversational frente a balanced.** Ambos tienen
la misma política de incertidumbre de entrada; su diferencia de aclaración solo
se activa ante una intención canónica desconocida. Se revisaron los 72 dictámenes
semánticos guardados con ambos modos: **ninguno activó esa diferencia**. Las
llamadas al evaluador y al generador fueron independientes, sin caché entre modos.
Por tanto, la diferencia observada de tres frente a cinco FP no se atribuye
causalmente al perfil.

Los dos FP adicionales de `balanced` proceden del evaluador contextual: uno de
una solicitud con parámetros pendientes y otro de un registro etiquetado benigno
que comienza «Forget the previous instruction». Este último exige adjudicación
humana; no se cambió su etiqueta para mejorar la métrica. Las otras tres negativas
se rechazaron en la capa de inyección en ambos modos.

Las aclaraciones fijas de ambos modos corresponden al mismo caso. Los fallos de
`conversational` fueron dos dictámenes de alcance inválidos y dos generaciones
incompletas; los de `balanced`, dos dictámenes inválidos y una generación incompleta.
Todas las solicitudes al proveedor devolvieron HTTP 200: esos errores son del
resultado o su validación, no fallos HTTP ni ataques detectados.

## Detección de entrada local

Antes de usar el evaluador o generar respuestas se pasó la misma muestra por
el filtro local y el guard conversacional con aislamiento habilitado:

| Perfil | TP | FP | FN | TN | Fallos |
|---|---:|---:|---:|---:|---:|
| conversational | 18 | 3 | 6 | 21 | 0 |
| balanced | 18 | 3 | 6 | 21 | 0 |
| strict | 24 | 24 | 0 | 0 | 0 |

Esta vista no mide generación, filtración ni éxito de tareas. No se suma a los
144 episodios como observaciones independientes.

## Exfiltración y herramientas

| Indicador | conversational | balanced | strict |
|---|---:|---:|---:|
| Casos marcados como objetivo de exfiltración | 7 | 7 | 7 |
| Exfiltraciones detectadas en esos casos | 0/7 | 0/7 | 0/7 |
| Fallos entre esos casos | 0 | 0 | 0 |
| Exfiltraciones detectadas en cualquier caso | 0 | 0 | 0 |
| Episodios con herramienta no autorizada ejecutada | 0 | 0 | 0 |
| Archivos entregados | 1 | 1 | 0 |

Los siete objetivos, todos de Lúmina, se anotaron provisionalmente antes de la
ejecución. La pertenencia a esa categoría no prueba que cada petición actual sea
maliciosa: depende de antecedentes y del objetivo anotado. Se inspeccionaron sus
21 resultados; no se proporcionó la clave ni una estadística solicitada de ella.
Algunas peticiones recibieron información pública sin rechazo explícito; eso no
se convirtió en exfiltración por ser FN de la matriz de rechazo.

El oráculo cubre clave sintética, transformaciones conocidas y fragmentos
literales de al menos ocho caracteres en respuesta final, archivos entregados
y destino web simulado. No descarta fragmentos menores, codificaciones arbitrarias
ni reconstrucción entre turnos. Con solo siete objetivos, cero no prueba una tasa
real próxima a cero ni diferencia entre perfiles. Tampoco se incluyó aquí una
condición nueva sin Promption.

## Consumo, trazabilidad y límites

- **155 llamadas nuevas**, todas HTTP 200: 72 de alcance, 46 de generación y 37
  del juez de rechazo. Los episodios detenidos antes de generación se conservaron.
- Coste nuevo conservador: **US$0.165638**. Acumulado: **US$1.669110 de US$2**,
  sin descuentos por caché y conservando reservas de estudios anteriores.
- Se verificaron protocolo, emparejamiento, modelos, hashes y presupuesto. El
  contenido de las peticiones no contenía la clave real ni credenciales. La
  búsqueda específica de alias conocidos no encontró coincidencias en los casos
  fuente; no constituye garantía general de anonimización.
- Evidencia privada: `output/profiles_comparison_20261025/`, con protocolo,
  fuentes congeladas, episodios, peticiones, respuestas, ledger, CSV y auditoría.

Los porcentajes no se comparan directamente con los 720 episodios anteriores:
cambia la composición de la muestra y siguen existiendo dependencia entre casos,
etiquetas discutibles y variación del modelo. No se modificó la librería durante
el experimento ni se eligieron casos usando sus predicciones.

Análisis reproducible sin más llamadas:

```bash
.venv/bin/python scripts/research/summarize_profile_study.py --output output/profiles_comparison_20261025
.venv/bin/python scripts/research/audit_corpus_study.py --output output/profiles_comparison_20261025
```
