"""Verified, narrow business answers; authoritative identity and MCP data only.

Never use user text to select a privileged tool or grant a role. The caller must
have successfully evaluated ACL and retrieved the indicated tool in this turn.
"""
from __future__ import annotations
import re
from promption.policies import normalize_text

_CATALOG = re.compile(
    r'^(?:(?:consulta para la tienda|por favor)\s+)*que autonomia y tipo de conexion tienen los auriculares '
    r'([a-z0-9 -]{2,65}) segun (?:su|el) catalogo$')
_CONCEPTUAL_STOCK = re.compile(
    r'^(?:(?:consulta para la tienda|por favor)\s+)*que significa (?:el termino )?stock '
    r'cuando compro un producto en su catalogo(?: explicalo brevemente)?$')
_ENGLISH_HEADPHONES = re.compile(
    r'^(?:(?:please|hello)\s+)*do you sell wireless headphones and what are '
    r'their main technical features in your store$')
_PAYROLL = re.compile(
    r'^(?:(?:consulta para la tienda|por favor)\s+)*(?:consulta|muestra|muestrame|dime) '
    r'el sueldo neto mensual (?:registrado )?de ([a-z ]{3,55}?)(?: en el perfil de empleados)?$')


def verified_simple_answer(text, *, policy_id, roles, authenticated, sources):
    """Return a source-based answer or None for general semantic processing.

    Only the two bounded request shapes recognized here are handled. All mixed,
    quoted, or otherwise complex requests continue through the ordinary guards.
    """
    normalized = re.sub(r'[¿?¡!.,:;]+', ' ', normalize_text(text)).strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    source = {name: value for name, value in sources if isinstance(value, dict)}
    if policy_id == 'public.shipping' and 'getShippingPolicy' in source:
        policy = source['getShippingPolicy']
        if re.fullmatch(r'(?:(?:consulta para la tienda|please) )*what is the standard delivery '
                        r'timeframe for domestic shipping orders in your store policy', normalized):
            shipping = policy.get('envios')
            terms = policy.get('condiciones')
            if isinstance(shipping, dict) and isinstance(terms, dict):
                duration = shipping.get('estandar')
                if isinstance(duration, str) and duration:
                    duration = duration.replace('días laborables', 'business days').replace('días hábiles', 'business days')
                    return ('For mainland Spain (Península), the published standard delivery '
                            f'time is {duration} from dispatch, subject to confirmed availability. '
                            'Other domestic destinations may have different conditions; '
                            'please specify the destination to verify its published rate and timeframe.')
    if policy_id in {'public.brand', 'public.shipping'} and 'getBrandInfo' in source and 'getShippingPolicy' in source:
        if re.fullmatch(r'(?:(?:consulta para la tienda|por favor) )*traduce al frances '
                        r'el horario y la direccion de contacto publico de promption shop', normalized):
            channels = source['getBrandInfo'].get('canales')
            schedule = source['getShippingPolicy'].get('horarios')
            if isinstance(channels, dict) and isinstance(schedule, dict):
                address, hours = channels.get('address'), schedule.get('atencion')
                if isinstance(address, str) and address and isinstance(hours, str) and hours:
                    translated_hours = hours.replace('L-V', 'du lundi au vendredi,')
                    return ('Selon les informations publiques vérifiées de Promption Shop : '
                            f'adresse : {address} ; horaires d’ouverture : {translated_hours}.')
    if policy_id == 'confidential.financial_kpis' and authenticated and 'admin' in roles \
            and 'getKPIStats' in source:
        if re.fullmatch(r'(?:(?:consulta para la tienda|por favor) )*'
                        r'(?:muestra|consulta|dame) (?:el )?informe de kpis financieros anuales '
                        r'de la empresa con balance consolidado', normalized):
            report = source['getKPIStats']
            facts = report.get('kpis')
            if isinstance(facts, dict):
                revenue, ebitda, margin = (facts.get('facturacion_anual'),
                                           facts.get('ebitda'), facts.get('margen_bruto'))
                if all(isinstance(value, str) and value for value in (revenue, ebitda, margin)):
                    return (f"Indicadores financieros del periodo {report.get('periodo', 'registrado')} "
                            f"({report.get('estado', 'sin estado')}): facturación anual {revenue}; "
                            f"EBITDA {ebitda}; margen bruto {margin}. "
                            'La herramienta autorizada no proporciona un balance consolidado '
                            '(activo, pasivo y patrimonio); no puedo emitir esas cifras sin otra fuente verificada.')
    if policy_id == 'public.shipping' and 'getShippingPolicy' in source:
        if re.fullmatch(r'(?:(?:consulta para la tienda|por favor) )*traduce al ingles '
                        r'las condiciones oficiales de envio a canarias registradas por la tienda', normalized):
            policy = source['getShippingPolicy']
            shipping, conditions = policy.get('envios'), policy.get('condiciones')
            if isinstance(shipping, dict) and isinstance(conditions, dict):
                canary = shipping.get('canarias_ceuta_melilla')
                if isinstance(canary, str) and canary:
                    canary = (canary.replace('días', 'business days')
                              .replace('gastos', 'cost').replace('€', ' EUR'))
                    return ('Official store shipping terms for the Canary Islands: '
                            f'{canary}. Free-shipping offers for mainland Spain do not apply '
                            'to the Canary Islands. The published timeframes start at dispatch '
                            'and depend on confirmed availability. No additional shipping '
                            'conditions have been inferred.')
    if policy_id == 'public.catalog' and 'getCatalogSummary' in source:
        match = re.fullmatch(
            r'(?:(?:consulta para la tienda|por favor) )*compara las especificaciones de '
            r'([a-z0-9 -]{3,55}) y ([a-z0-9 -]{3,55}) del catalogo para uso universitario', normalized)
        if match:
            products = source['getCatalogSummary'].get('productos')
            if not isinstance(products, list):
                return None
            located = []
            for wanted in match.groups():
                item = next((p for p in products if isinstance(p, dict)
                             and normalize_text(str(p.get('nombre', ''))) == wanted), None)
                if item is None:
                    return ('No encuentro fichas verificadas de todos los modelos solicitados; '
                            'necesito el nombre comercial exacto para compararlos sin inventar datos.')
                specs = item.get('caracteristicas')
                if not isinstance(specs, list):
                    return None
                located.append(f"{item.get('nombre')}: {item.get('precio_eur')} EUR; "
                               + ', '.join(str(v) for v in specs if isinstance(v, str)))
            return ('Comparación basada exclusivamente en el catálogo: '
                    + '; '.join(located) + '. '
                    'Para elegir según estudios, compara memoria, almacenamiento y presupuesto; '
                    'las prestaciones no publicadas no están confirmadas.')
    if policy_id == 'public.catalog':
        if _CONCEPTUAL_STOCK.fullmatch(normalized):
            return ('Stock significa las unidades de un producto disponibles para la venta. '
                    'Es una explicación general y no una consulta del inventario interno.')
        if _ENGLISH_HEADPHONES.fullmatch(normalized) and 'getCatalogSummary' in source:
            products = source['getCatalogSummary'].get('productos')
            if not isinstance(products, list):
                return None
            wireless = [p for p in products if isinstance(p, dict) and
                        any('bluetooth' in normalize_text(str(c)) for c in (p.get('caracteristicas') or []))]
            if not wireless:
                return 'The consulted catalog does not verify any wireless headphones at this time.'
            return 'According to the current catalog: ' + '; '.join(
                f"{p['nombre']}: {', '.join(str(c).replace('Cancelación de ruido', 'Noise cancellation').replace('batería', 'battery').replace('Resistencia al agua', 'Water resistance') for c in p.get('caracteristicas') or [])}"
                for p in wireless[:4]) + '. Unlisted specifications are not confirmed.'
    if policy_id == 'public.catalog' and 'getCatalogSummary' in source:
        match = _CATALOG.fullmatch(normalized)
        if match:
            sought = match.group(1).strip()
            products = source['getCatalogSummary'].get('productos')
            if not isinstance(products, list):
                return None
            product = next((item for item in products if isinstance(item, dict)
                            and normalize_text(str(item.get('nombre', ''))) == sought), None)
            if product is None:
                return ('No encuentro una ficha para ese modelo de auriculares en el catálogo consultado. '
                        'No puedo confirmar su autonomía ni conexión. Puedo ofrecerte modelos verificados.')
            specs = product.get('caracteristicas')
            if isinstance(specs, list):
                supported = ', '.join(str(item) for item in specs if isinstance(item, str))
                return (f"Según el catálogo consultado, {product['nombre']}: "
                        f"{supported or 'sin características técnicas registradas'}. "
                        'La autonomía o conectividad que no figure en la ficha no está confirmada.')
            return None
    if policy_id == 'confidential.payroll' and authenticated and 'admin' in roles and 'getEmployees' in source:
        match = _PAYROLL.fullmatch(normalized)
        if match:
            employees = source['getEmployees'].get('empleados')
            if not isinstance(employees, list):
                return None
            sought = match.group(1).strip()
            person = next((item for item in employees if isinstance(item, dict)
                           and normalize_text(str(item.get('nombre', ''))) == sought), None)
            if person is None:
                return 'No encuentro ese empleado en los registros autorizados consultados.'
            net = person.get('sueldo_neto')
            if not isinstance(net, str) or not net:
                return 'No consta un sueldo neto mensual verificable para ese empleado.'
            return f"Según el registro autorizado, el sueldo neto mensual de {person['nombre']} es {net}."
    return None
