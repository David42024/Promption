"""Detección ligera de idioma (es/en) por marcadores léxicos.

Sin dependencias nuevas: los embeddings son multilingües, pero el
entrenamiento y las métricas necesitan saber en qué idioma está cada
fila para estratificar y evaluar por separado.
"""

_ES_MARKERS = (
    "las instrucciones", "instrucciones", "anula tus restricciones", "restricciones éticas",
    "desconéctate", "directriz", "directrices", "indicación", "desordena", "ignora", "olvida", "revela",
    "sus reglas", "mis órdenes", "mis directrices", "configuración", "ética",
    "el prompt", "entrenamiento", "tus instrucciones", "tus reglas", "oculta", "secreto",
    "contraseña", "código", "revelar", "traduce", "finge", "actúa", "estás", "qué",
    "información", "seguridad", "confidencial", "sin restricciones", "haz caso omiso",
    "dime", "cuál", "dónde", "está", "tú", "también", "están", "tienes", "quiero que",
    "claves", "permiso", "denegado", "usted", "eres un", "imagina que", "supón que",
    "hola", "gracias", "estás", "estamos", "para que", "porque", "también", "cómo",
)

_PT_NEGATIVES = ("ã", "õ", "ç", "ê", "você", "tivesses", "fosses", "estejas", "teu ", "tua ")


def is_spanish(prompt: str) -> bool:
    low = (prompt or "").lower()
    if any(n in low for n in _PT_NEGATIVES):
        return False
    return any(m in low for m in _ES_MARKERS)


def detect_lang(prompt: str) -> str:
    """'es' si hay marcadores españoles, 'en' en caso contrario."""
    return "es" if is_spanish(prompt or "") else "en"
