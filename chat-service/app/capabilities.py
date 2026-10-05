"""Describe the shop features that the current session can actually use."""
import re

from promption.policies import normalize_text


CAPABILITY_LABELS = {
    "make_document": "Crear y adjuntar archivos DOCX, PDF, XLSX, CSV y TXT en este chat",
    "getBrandInfo": "Consultar información de la tienda",
    "getShippingPolicy": "Consultar envíos y devoluciones",
    "getCatalogSummary": "Consultar el catálogo",
    "getPromotions": "Consultar promociones",
    "getStockInfo": "Consultar existencias",
    "getMarketingCampaigns": "Consultar campañas de marketing",
    "getEmployees": "Consultar datos del personal",
    "getVIPClients": "Consultar clientes VIP",
    "getKPIStats": "Consultar indicadores del negocio",
    "getRevenueReport": "Consultar facturación mensual",
    "getTopProducts": "Consultar productos destacados",
    "ask_user": "Mostrar un cuadro de diálogo para solicitar un dato necesario",
    "attach_existing_document": "Adjuntar un documento autorizado",
    "web_search": "Buscar información pública en internet",
    "web_open": "Leer páginas web públicas",
}

_QUESTION = re.compile(
    r"(?:hola+|buenas|oye)?[\s,!.¿?]*"
    r"(?:(?:dime|cuentame|explicame|muestrame|lista|enumera)\s+)?"
    r"(?:(?:que|(?:todo\s+)?lo\s+que)\s+(?:puedes|puedo|podemos)\s+(?:hacer|ahcer|hcaer)"
    r"|que\s+(?:haces|sabes\s+hacer|servicios\s+ofreces)"
    r"|(?:cuales\s+son\s+)?(?:tus|mis|las)\s+(?:capacidades|funciones|permisos|herramientas)"
    r"(?:\s+(?:disponibles|actuales|autorizadas))?"
    r"|(?:en\s+que|como)\s+(?:me\s+)?puedes\s+ayudar(?:me)?"
    r"|que\s+(?:funciones|herramientas)\s+(?:tienes|tengo))"
    r"(?:\s+(?:en\s+(?:este\s+)?(?:chat|promption\s+shop)|con\s+mi\s+(?:cuenta|sesion)|por\s+mi))?"
    r"(?:\s+y\s+que\s+no(?:\s+puedes\s+hacer)?)?"
    r"[\s,!.¿?]*(?:por\s+favor|porfa)?[\s,!.¿?]*"
)
_GREETING = re.compile(
    r"(?:hola+|buenos dias|buenas tardes|buenas noches|hello|hi|hey)"
    r"(?:[, ]+¿?(?:como estas|que tal))?[\s.!¡¿?]*"
)


def is_capabilities_question(text: str) -> bool:
    """Recognize standalone feature questions, preserving checks for mixed requests."""
    return _QUESTION.fullmatch(normalize_text(text)) is not None


def is_simple_greeting(text: str) -> bool:
    """Recognize standalone greetings that do not need semantic classification."""
    return _GREETING.fullmatch(normalize_text(text)) is not None


def describe_capabilities(tool_specs: list[dict], *, authenticated: bool) -> str:
    """Render only the tool catalog already authorized by the server."""
    lines = ["Puedo ayudarte con Promption Shop: productos, compras, envíos, garantías "
             "e información pública de la tienda."]
    if not authenticated:
        lines.append("Estás como visitante sin sesión. Puedo consultar información pública "
                     "de la tienda mediante MCP; para crear archivos debes iniciar sesión.")
    elif tool_specs:
        lines.append("Con tu sesión actual tienes disponibles estas funciones:")
        for spec in tool_specs:
            name = spec["function"]["name"]
            if name in CAPABILITY_LABELS:
                lines.append("- " + CAPABILITY_LABELS[name])
    else:
        lines.append("No hay herramientas disponibles para tu sesión en este momento.")
    lines.append("Solo puedo trabajar con los datos autorizados para tu cuenta y dentro "
                 "del alcance de la tienda. No envío archivos por correo ni cambio permisos.")
    return "\n\n".join(lines)
