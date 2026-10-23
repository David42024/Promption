# Contexto, intención y clasificadores pequeños — Promption 1.3.0

## Decisión e investigación

La evaluación conjunta de intención y alcance recibe petición actual, historial,
política confiable, identidad del servidor y herramienta propuesta. Usa una llamada
estructurada por contexto evaluado; no añade otra llamada separada para intención.
Los cambios de contexto y las propuestas de herramientas requieren su propia evaluación.
La integración anterior se mantiene compatible.

| Sistema | Mecanismo documentado | Aplicación a Promption |
| --- | --- | --- |
| [NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/v0.24.0/reference/colang-architecture-guide) | Genera intención canónica con ejemplos e historial antes de decidir acciones. | Intención explícita y resolución de referencias. No se replica su motor Colang. |
| [Meta Prompt Guard 2](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M) | Clasificador especializado; 86M usa mDeBERTa multilingüe, evaluada en español; ventana de 512 tokens. | Candidato para evaluación local y segmentación por tokens. La versión 22M tiene una brecha multilingüe mayor. |
| [Microsoft Prompt Shields](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-filter-prompt-shields) | Distingue ataques de usuario y documentos; la integración declara el origen. No determina alineación con tarea/política. | Separación entre origen, autoridad y autorización contextual. |
| [Lakera Guard](https://docs.lakera.ai/api-reference/lakera-api/guard/screen-content) | Recibe historial y definiciones de herramientas; resultados por detector y mensaje/herramienta. | Evaluación previa a efectos y metadatos estructurados. No se integra su API externa. |
| [ProtectAI DeBERTa v2](https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2) | Ajustado para inglés; ficha declara limitaciones fuera del inglés y proyecto archivado. | Referencia comparativa; no se elige como detector principal para español. |

Fuentes primarias consultadas el 23/10/2026. Las cifras de proveedores no son
resultados de Promption ni una comparación controlada con nuestros datos.

## Contrato contextual

```json
{
  "classification": "IN_SCOPE",
  "reason": "in_scope",
  "intent": {
    "name": "document_creation",
    "attack": "none",
    "relation": "follow_up",
    "origin": "none",
    "confidence": 0.95,
    "evidence": [0, 1]
  }
}
```

`name` describe una intención canónica acotada; `attack` identifica ataques
independientemente del tema; `relation` distingue petición autónoma, continuación,
cita y referencia no resuelta; `origin` atribuye el ataque a usuario, herramienta
o ambos; `evidence` contiene índices del historial, sin citas ni razonamiento libre.
`confidence` es una estimación del evaluador, **no una probabilidad calibrada**.

Se validan categorías, coherencia, límites y procedencia. Una continuación sin
antecedente o una herramienta inexistente no autoriza operaciones. Baja confianza
produce ambigüedad; respuesta inválida o proveedor caído son fallos operativos,
no ejemplos positivos de ataque para entrenamiento.

| Texto actual | Antecedente | Interpretación esperada con política de datos públicos |
| --- | --- | --- |
| «expórtalo» | Catálogo público | Documento permitido |
| «expórtalo» | Extraer clave privada | Operación prohibida |
| «explícame este ataque» | Ejemplo citado para formación autorizada | Discusión de seguridad si la política la admite |
| «resume la página» | Página que ordena cambiar permisos | Inyección indirecta desde datos externos |
| «holaaa» | Ataque anterior sin relación con el saludo | Saludo legítimo para el evaluador contextual |

El último caso no elimina automáticamente un veto previo del filtro de conversación:
la semántica nueva no desactiva la lógica OR ni borra historial malicioso. Una aprobación
contextual nunca anula vetos de entrada, ML, ACL o salida. La discusión de seguridad
solo está permitida cuando la política de la aplicación la admite.

## AI SDK 6

Reemplazar `createScopeEvaluator` por `createContextEvaluator`. `classifierModel`
debe soportar salida estructurada; las demás variables pertenecen a la integración.

```ts
import { createPromption, createContextEvaluator } from '@promption/ai-sdk';
import { wrapLanguageModel } from 'ai';

const protection = createPromption({
  transport: guardTransport,
  scopeEvaluator: createContextEvaluator({
    model: classifierModel, minimumConfidence: 0.8, timeoutMs: 30_000,
  }),
  onScope: result => audit.write(result),
});
const model = wrapLanguageModel({
  model: responseModel,
  middleware: protection.middleware({
    identity: serverIdentity,
    systemPrompt: serverPolicy,
    securityMessages: serverHistory,
    toolPolicies: serverToolPolicies,
  }),
});
```

El evaluador no tiene herramientas ejecutables. La política va en `system`; historial
y argumentos son datos. El middleware reevalúa las herramientas propuestas antes de
sus efectos y conserva controles de entrada, conversación, ACL y salida. Respeta
cancelación y plazos. La caché vincula petición, historial, identidad, política y herramienta.

El historial se reconstruye en el servidor: «soy admin» no cambia el rol real.
La biblioteca no almacena conversaciones ni autentica contenido del cliente.
Límites actuales: 128 mensajes, 100000 caracteres de evidencia incluyendo petición y
herramienta, política con límite propio de 50000 caracteres.

Si la integración usa recibos de alcance firmados, usar un identificador de perfil
nuevo: no reutilizar aprobaciones del evaluador anterior. El adaptador de recibos
existente no guarda `intent`; no usarlo cuando se requiera anotación en cada auditoría.

## Python

```python
from promption import Promption, ContextScopeGuard, AsyncContextScopeGuard

protection = Promption(scope_guard=ContextScopeGuard(evaluate_context))
async_guard = AsyncContextScopeGuard(evaluate_context_async, timeout_seconds=30)
```

Los evaluadores son funciones inyectadas: reciben el contrato de `ScopeGuard`
(`text`, `system_prompt`, `messages`, `identity`, `tool` si corresponde) y devuelven
la respuesta estructurada anterior. Python valida el resultado; no conecta un modelo
automáticamente ni obtiene contexto ausente. `async_guard` se conecta a
`AsyncGuardPipeline(scope_guard=async_guard, ...)`.

## Clasificador pequeño opcional

```bash
pip install 'promption[small-models]'
```

```python
from promption.filter import EnsembleFilter, SmallModelFilter

detector = SmallModelFilter.from_pretrained(
    '/ruta/local/pesos-prompt-guard-2',
    positive_labels=('MALICIOUS',), threshold=0.9,
    local_files_only=True, max_tokens=512, overlap_tokens=128,
)
input_filter = EnsembleFilter(additional_filters=[detector])
```

Se usan Transformers y PyTorch oficiales, sin implementar DeBERTa desde cero.
Las dependencias son opcionales. El umbral `0.9` es ilustrativo, **no validado** para
este corpus. El adaptador no instala ni activa pesos por defecto. Prompt Guard 2
requiere acceso autorizado; no se descarga ni acepta una licencia por el usuario.
Para un identificador remoto autorizado puede indicarse `local_files_only=False`
y fijar `revision` a un commit revisado.

La carga exige Safetensors y deshabilita código remoto; busca los nombres positivos
en `id2label` sin asumir índice 1. Reserva tokens especiales y puntúa todas las
ventanas solapadas, usando el máximo. Lotes y cantidad de ventanas están acotados;
exceder el límite da error en lugar de aceptar un prefijo truncado. Fallos de carga
o inferencia son errores ML tipados, no detecciones de ataque.

## ¿Mejoraría BERT/DeBERTa?

Es una hipótesis razonable para patrones semánticos que TF-IDF no capture, con un
clasificador especializado multilingüe y ajuste de dominio. Un BERT genérico no basta.
Un detector binario tampoco resuelve permisos particulares sobre datos de la aplicación.
La propuesta combina detector especializado, contexto y controles de permisos/salida.
Añadir un veto OR puede reducir FN **y aumentar FP**: no se activa por defecto ni
se afirma una ganancia sin medirla.

Para el artículo, comparar versiones congeladas: anterior, anterior con contexto,
anterior con clasificador y combinación. Separar usuarios y familias entre train/val/test;
calibrar umbrales solo en validación y revisar etiquetas humanas a ciegas. Incluir
pares con mismo texto y distinto contexto, herramientas, coloquialismos y conversaciones
largas. Medir FP/FN, precision/recall, ASR extremo a extremo, utilidad, coste y latencia,
con intervalos de confianza agrupados por participante. Los registros existentes
son etiquetas provisionales y no constituyen un nuevo test ciego.

## Verificación inicial sin proveedor

Las pruebas nuevas usan evaluadores y tensores sintéticos: verifican contratos,
procedencia, coherencia, aislamiento, bloqueo previo a efectos y ventanas completas.
No miden precisión de un LLM ni de pesos DeBERTa reales. En esa verificación inicial no se enviaron chats a OpenAI,
se reentrenaron esos pesos ni se desplegó la app. Las métricas exploratorias de 1.2.0
no se atribuyen a estas funciones nuevas.

### Diagnóstico con proveedor real posterior

La primera prueba con GPT-5.4-mini ejecutó 100 llamadas sobre 50 casos pareados
(40 mensajes reales seudonimizados y 10 controles). El evaluador contextual produjo
31 fallos de validación/no disponibilidad y 19 rechazos semánticos; no autorizó
ningún caso. Esa versión no permite afirmar una mejora de FP/FN. Los fallos se
conservan aparte de las detecciones y afectan la disponibilidad para el usuario.

El parche del SDK 1.3.1 restringe en el propio esquema las combinaciones entre ataque
y origen: sin ataque, origen `none`; con ataque, origen no confiable obligatorio.
Añade descripciones para evitar confundir origen del mensaje con origen del ataque.
Una evaluación inválida conserva el consumo y se informa como `invalid_scope_response`.
El parche mantiene el bloqueo ante incoherencias y pasó 86 pruebas JavaScript y tipos.
La causa exacta de cada respuesta inicial no puede reconstruirse porque no se guardaron
salidas crudas; esta corrección trata una ambigüedad verificable del contrato.
La repetición posterior con proveedor real está documentada en
[evaluación de FP/FN](fp_fn_evaluation_20261023.md). Usó 48 llamadas adicionales y se
detuvo ante un fallo de procedencia en una propuesta de herramienta. En 37 casos reales
pareados, los FN semánticos pasaron de 3 a 2 y los FP permanecieron en 0; combinando
las capas de entrada, ambos perfiles conservaron 1 FP y 1 FN.

La versión 1.3.2 admite la herramienta propuesta como origen de un ataque cuando
existe realmente en la petición (`name` e `input`), sin inventar un mensaje histórico.
Los índices citados siguen teniendo que existir y una detección de ataque nunca puede
autorizar la operación. Esta última corrección se verificó localmente; no se hizo
otra repetición con OpenAI. No se desplegó la aplicación.
