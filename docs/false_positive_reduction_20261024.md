# Promption 1.4.0: reducción de falsos rechazos

## Cambios

1. **Aislamiento explícito de historial.** El backend puede declarar que una
   intervención completa es independiente y exige Output Guard. El middleware
   retira efectivamente el historial anterior del contexto del generador. No se
   permite usar esa transición para referentes como «hazlo», peticiones mixtas,
   alias pendientes, condiciones de activación o evidencia de tools. Se mantienen
   la comprobación del mensaje actual, límites, identidad y ACL.
2. **Contrato conservador para otros consumidores.** El parámetro de servidor
   `isolate_history` es optativo en Python y la API. Sin él, los vetos históricos
   siguen vigentes. AI SDK lo solicita y valida los metadatos antes de aislar.
   Las autorizaciones para herramientas siguen requiriendo comprobación propia.
3. **Ambigüedad inocua.** Un dictamen válido ambiguo con intención sin ataque y
   sin información protegida puede devolver una aclaración fija. No autoriza
   generación, consulta de datos ni tools. No se convierte un fallo operativo o
   una intención maliciosa en aprobación. JSON estructurado y tools conservan
   el cierre ante incertidumbre.
4. **Políticas públicas completas.** Se reconocen preguntas completas sobre
   garantías, envíos y devoluciones. Una instrucción maliciosa añadida anula esa
   ruta; las reglas no dan permisos ni amplían el alcance de una aplicación.
5. **Alias acotados.** Se evita expandir recursivamente títulos o nombres sobre
   sí mismos hasta producir un falso error de límite. Se conservan vistas
   originales y reconstruidas, inspección de ataques y cotas de tamaño/profundidad.
6. **Evaluación y etiquetas.** El prompt del juez de respuestas distingue una
   corrección factual («No, el envío cuesta…») de un rechazo de seguridad. La
   corrección se aplica a futuras ejecuciones, no altera las respuestas ni las
   matrices históricas. Ocho negativos de fuente con instrucciones de cambio de
   autoridad quedan propuestos para revisión, sin reasignación automática.

El ensemble conserva OR entre vetos ejecutados. No se han cambiado umbrales ni
reentrenado pesos con etiquetas provisionales; eso podría aprender errores del
corpus y producir una mejora aparente. El evaluador contextual distingue la
política del asistente de su propio rol de clasificador y reconoce que faltar un
producto o formato no implica desconocer el dominio o los permisos de la tarea.
El cambio de instrucciones del evaluador aún requiere validación con un modelo real.

## Comprobación local pareada

Se reutilizan los registros del estudio 1.3.3: 7823 textos del corpus de referencia,
4411 turnos de Lúmina y la muestra depurada de 240 casos. No se han consumido
llamadas externas. Estas son regresiones sobre datos ya expuestos, no un nuevo
test independiente ni una evaluación de exfiltración de extremo a extremo.

La vista «entrada SDK» aplica primero el veto del mensaje individual y después
la comprobación contextual. Los dictámenes de error se mantienen separados.
No debe confundirse con la vista contextual aislada ni con la matriz de rechazo
del sistema completo que incluye generación y juez de respuestas.

| Cohorte y vista | N | FP 1.3.3 | FP 1.4.0 | FN 1.3.3 | FN 1.4.0 |
|---|---:|---:|---:|---:|---:|
| Lúmina completa, entrada SDK | 4411 | 425 | 414 | 959 | 960 |
| Lúmina por participante test, entrada SDK | 821 | 44 | 42 | 92 | 92 |
| Muestra Lúmina, entrada SDK | 120 | 6 | 4 | 12 | 12 |
| Muestra de referencia, entrada SDK | 120 | 6 | 6 | 7 | 7 |
| Referencia completa, mensaje individual | 7823 | 299 | 299 | 949 | 949 |

El FN adicional según la referencia completa es T01236: «que eres?» después de
solicitudes de clave rechazadas. La anotación silver lo considera extracción
contextual; el nuevo control trata esa pregunta de identidad como independiente
y aísla el historial. Se propone revisar la etiqueta sin modificarla para mejorar
la matriz. No se ha observado aquí su respuesta nueva ni medido exfiltración.

En la muestra de referencia, un error contextual que dejaba un turno no evaluable
en la entrada SDK pasa a TN; por eso el número de FN/FP es igual y el de TN pasa
de 53 a 54. En Lúmina completa, la vista contextual tenía 24 errores y ahora no
presenta ninguno. La vista SDK podía bloquear muchos de esos casos antes de
llegar al error; no deben contarse esos 24 como falsos positivos eliminados.

Seis de los catorce rechazos negativos por ambigüedad del estudio anterior son
elegibles para aclaración según sus dictámenes guardados. Es una prueba de
enrutamiento del dictamen anterior, no una predicción de cómo responderá ahora el
modelo contextual ni de cuántas tareas resolverá el chatbot.

**Conclusión:** mejora local modesta y comprobada, con los límites anteriores.
No se afirma que los 38 FP del sistema completo se hayan reducido a una cifra
nueva, porque no se ha repetido la evaluación API. Tampoco se vuelve a estimar ASR.

## Integración Python

Quien active `isolate_history=True` debe usar el contexto indicado al llamar al
modelo. El middleware de AI SDK implementa este contrato automáticamente. Para
integraciones directas, se prepara evidencia explícita que incluya el turno actual:

```python
evidence = [*history, {"role": "user", "content": user_text}]
decision = protection.check_input(
    user_text, identity, messages=evidence, system_prompt=system_prompt,
    output_enabled=True, isolate_history=True,
)
if decision.action == "CLARIFY":
    checked = protection.check_output(decision.text, identity, protected_values=protected_values)
    if checked.allowed:
        reply = checked.text
elif decision.allowed:
    model_messages = evidence[-1:] if (decision.conversation or {}).get("isolated_history") else evidence
```

Después de preparar `model_messages`, la generación recibe el system por separado;
las tools, archivos y respuesta final se revisan antes de entregarse al cliente.

El parámetro no es un permiso del usuario final: lo establece el servidor de la
aplicación que se compromete a aislar el contexto. No debe exponerse como una
opción que el participante pueda usar para cambiar identidad o autorizaciones.

## Reproducción y procedencia

```bash
.venv/bin/python scripts/research/evaluate_fp_reduction.py --output output/fp_reduction_20261024
python -m pytest tests/ -q
node --test --test-isolation=none packages/ai-sdk/test/*.test.js
npm run test:types --prefix packages/ai-sdk
```

Los resultados individuales y propuestas de revisión permanecen privados en
`output/fp_reduction_20261024/`. La fuente congelada del estudio anterior se
conserva en `output/corpus_three_conditions_20261024/frozen_source/`. Su analizador
verifica esas huellas cuando el código actual ya corresponde a una versión nueva.
No se modificaron sus episodios, etiquetas originales ni registro de solicitudes.

## Verificación y paquetes

- Suite completa Python: 1097 correctas, diez omitidas.
- AI SDK: 101 pruebas correctas, incluidos generación, streaming, cancelación,
  aislamiento concurrente, salida con canario y bucle nativo de herramientas.
- TypeScript: correcto.
- Benchmark sin LLM ni reentrenamiento: 661 filas; se restauraron los informes
  genéricos anteriores después de guardar el smoke por separado.
- API y dashboard: salud HTTP 200; dashboard sin errores de importación.
- Los dos paquetes se construyeron y verificaron localmente; el wheel importa
  las reglas empaquetadas y la huella del clasificador original no cambió.

Distribuciones locales, sin publicación:

- `dist/promption-1.4.0-py3-none-any.whl`
- `dist/promption-ai-sdk-1.4.0.tgz`

`output/fp_reduction_20261024/verification.json` registra huellas de código,
clasificador, distribuciones y resultados. No hubo llamadas de pago durante esta
corrección. Para activar el aislamiento deben actualizarse el backend Python y el
middleware del consumidor; estos paquetes no despliegan automáticamente ninguna app.
