# Solicitudes de extracción en español

La regla `reveal_internal_prompt_es` detecta solicitudes de ver, copiar, revelar
o compartir el prompt base, el prompt del sistema y las instrucciones internas.
Se distribuye en ambos archivos de heurísticas. Las menciones educativas y la
redacción de un prompt propio no coinciden por la mera presencia de esas palabras.
Las reglas siguen siendo aproximaciones léxicas; sus resultados requieren revisión
en consultas ambiguas.

`promption/training/spanish_security_corpus.py` contiene 24 parejas de ataques
claros y consultas legítimas relacionadas. Sus cuatro variantes producen 192
filas equilibradas, agrupadas en 48 familias. Los ataques solicitan extracción
de información interna, credenciales, evasión de permisos o ejecución de órdenes
no confiables. Los ejemplos legítimos usan información pública, conceptos y
datos ficticios. Son ejemplos nuevos redactados para entrenamiento; no son
traducciones de casos reservados ni evidencias independientes de eficacia.

Para agregar este corpus a un modelo ligero que ya contiene traducciones:

```powershell
python -c "from promption.training.spanish_security_corpus import build_reviewed_spanish_corpus; build_reviewed_spanish_corpus().to_csv('data/results/spanish-security-v2-corpus.csv', index=False)"
python scripts/retrain_lightweight_spanish.py --execute --additional-corpus data/results/spanish-security-v2-corpus.csv
```

El script conserva los grupos y particiones existentes, rechaza duplicados y
familias ya instaladas, y agrega los ejemplos únicamente a entrenamiento.
Guarda candidato, metadatos, manifiesto y comparación en un directorio nuevo.
`--activate` solo instala el candidato si supera las comprobaciones de validación:
recall general y español sin pérdida, FPR español sin aumento y FPR general
con aumento máximo de un punto porcentual. No se cambian los umbrales para
aprobar un candidato.

En la ejecución del 10 de octubre de 2026, ni el candidato de 192 variantes ni
el conservador de 48 semillas superaron el requisito de recall general.
Se mantuvieron el modelo activo y sus datos de entrenamiento. La nueva regla
heurística sí está disponible en el código; los servicios deben recargar sus
reglas mediante reinicio o despliegue para utilizarla.
