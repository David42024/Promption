"""Bounded, source-derived fallback when repeated MCP tool calls make no progress.

The caller must pass results of successfully authorized tools in the CURRENT turn,
and still apply Output Guard and output policy before delivering any response.
"""
from typing import Any


def verified_tool_fallback(text: str, sources: list[tuple[str, Any]]) -> str | None:
    source = {name: value for name, value in sources if isinstance(value, dict)}
    if 'getBrandInfo' in source:
        brand = source['getBrandInfo']
        channels = brand.get('canales') or {}
        if not isinstance(channels, dict):
            return None
        if any(word in text.casefold() for word in ('francés', 'frances', 'french')):
            return ('Informations vérifiées de la boutique : '
                    f"adresse : {channels.get('address', 'non renseignée')}; "
                    f"téléphone : {channels.get('phone', 'non renseigné')}; "
                    f"courriel : {channels.get('email', 'non renseigné')}. "
                    'Les horaires ne figurent pas dans ces données de contact; '
                    'ils doivent être vérifiés avant leur traduction.')
        return ('Información pública verificada de la tienda: '
                f"dirección: {channels.get('address', 'no disponible')}; "
                f"teléfono: {channels.get('phone', 'no disponible')}; "
                f"correo: {channels.get('email', 'no disponible')}.")
    if 'getShippingPolicy' in source:
        policy = source['getShippingPolicy']
        conditions = policy.get('condiciones') or {}
        shipping = policy.get('envios') or {}
        if not isinstance(conditions, dict) or not isinstance(shipping, dict):
            return None
        threshold = conditions.get('umbral_envio_gratis_eur')
        region = conditions.get('envio_gratis_region')
        if threshold is None or not region:
            return None
        condition = 'superiores a' if conditions.get('umbral_inclusivo') is False else 'desde'
        return (f"Según la política de envíos consultada, el envío gratuito en {region} "
                f"se aplica a pedidos {condition} {threshold} €. "
                f"El plazo estándar publicado es {shipping.get('estandar', 'no disponible')}. "
                'No se han supuesto condiciones adicionales.')
    if 'getCatalogSummary' in source:
        products = source['getCatalogSummary'].get('productos') or []
        if not isinstance(products, list) or not products:
            return None
        mentioned = [p for p in products if isinstance(p, dict) and isinstance(p.get('nombre'), str)
                     and p['nombre'].casefold() in text.casefold()]
        if mentioned:
            lines = []
            for product in mentioned[:3]:
                specs = ', '.join(map(str, product.get('caracteristicas') or []))
                lines.append(f"{product['nombre']}: {specs or 'sin características documentadas'}")
            return 'Datos verificados del catálogo: ' + '; '.join(lines) + '. No se han añadido especificaciones.'
        if any(w in text.casefold() for w in ('características', 'autonomía', 'precio', 'especificaciones')):
            return ('No encontré una ficha que coincida claramente con el modelo solicitado '
                    'en el catálogo recuperado. Puedo mostrar alternativas verificadas o ayudarte '
                    'a identificar el nombre comercial exacto.')
    return None
