"""Versioned, synthetic Shop knowledge consumed only by the existing MCP tools."""
from copy import deepcopy


_CATEGORIES = ["Smartphones", "Laptops", "Tablets", "Accesorios", "Smart Home", "Gaming"]
_PRODUCT_ROWS = [
    ("SP-IPH-15-128", "iPhone 15", "Smartphones", 750, ["128 GB", "5G", "USB-C"]),
    ("SP-IPH-15-P-256", "iPhone 15 Pro", "Smartphones", 1199, ["256 GB", "5G", "Titanio"]),
    ("LT-MBA-M3", "MacBook Air M3", "Laptops", 1500, ["16 GB RAM", "512 GB SSD", "13 pulgadas"]),
    ("LT-OFFICE-GO", "OfficeBook Go", "Laptops", 549, ["8 GB RAM", "256 GB SSD", "Uso oficina"]),
    ("LT-THINK-WORK", "ThinkWork 14", "Laptops", 1199, ["16 GB RAM", "1 TB SSD", "14 pulgadas"]),
    ("LT-CREATOR-16", "CreatorBook 16", "Laptops", 2199, ["32 GB RAM", "1 TB SSD", "Diseño y gaming"]),
    ("TB-NOTE-10", "TabNote 10", "Tablets", 349, ["128 GB", "10 pulgadas", "Lápiz compatible"]),
    ("TB-PRO-12", "TabPro 12", "Tablets", 699, ["256 GB", "12 pulgadas", "Teclado opcional"]),
    ("AU-SOUND-PEAK", "SoundPeak WH-1000XM5", "Accesorios", 399, ["Cancelación de ruido", "30 h batería", "Bluetooth"]),
    ("AU-BUDS-PRO", "Buds Pro 2", "Accesorios", 229, ["Cancelación activa", "USB-C", "Resistencia al agua"]),
    ("AC-WEBCAM-4K", "Webcam 4K Pro", "Accesorios", 129, ["4K a 30 fps", "USB", "Micrófonos duales"]),
    ("SH-MESH-2", "Mesh Home Duo", "Smart Home", 199, ["Wi-Fi 6", "Dos nodos", "Control por aplicación"]),
    ("SH-PLUG-1", "Smart Plug Mini", "Smart Home", 29, ["Wi-Fi", "Medición de consumo", "Temporizador"]),
    ("GM-MOUSE-PRO", "StrikeMouse Pro", "Gaming", 89, ["Inalámbrico", "120 h batería", "Sensor 26K DPI"]),
    ("GM-KEYBOARD-RGB", "MechKeyboard RGB", "Gaming", 149, ["Switches rojos", "Cableado", "Aluminio"]),
    ("GM-PAD-X", "GamingPad X", "Gaming", 69, ["PC y consola", "Inalámbrico", "Vibración"]),
]
_PRODUCTS = [{"sku": sku, "nombre": name, "categoria": category, "precio_eur": price,
              "caracteristicas": features, "garantia_meses": 24}
             for sku, name, category, price, features in _PRODUCT_ROWS]
_PRODUCT_BY_SKU = {product["sku"]: product for product in _PRODUCTS}
_EMPLOYEE_ROWS = [
    ("Ana García", "Agente Senior", "Ventas", 1800, 28800, 92),
    ("Carlos Martín", "Agente Junior", "Ventas", 1500, 24000, 78),
    ("Laura Fernández", "Jefa de Marketing", "Marketing", 2700, 43200, 88),
    ("Director General", "Dirección", "Dirección", 4200, 67200, 99),
    ("Miguel Torres", "Responsable de Logística", "Logística", 2400, 38400, 84),
    ("Elena Prado", "Agente de Ventas", "Ventas", 1700, 27200, 81),
    ("Diego Soler", "Agente de Ventas", "Ventas", 1650, 26400, 79),
    ("Lucía Vega", "Atención al Cliente", "Soporte", 1600, 25600, 87),
    ("Pablo Ríos", "Técnico de Soporte", "Soporte", 1900, 30400, 90),
    ("Sara Montes", "Analista de Marketing", "Marketing", 2100, 33600, 86),
    ("Iván Luna", "Gestor de Compras", "Compras", 2200, 35200, 85),
    ("Clara Vidal", "Contabilidad", "Finanzas", 2300, 36800, 91),
    ("Hugo Marín", "Operador de Almacén", "Logística", 1550, 24800, 80),
    ("Nora Campos", "Operadora de Almacén", "Logística", 1550, 24800, 83),
    ("Adrián Soto", "Técnico de Sistemas", "Sistemas", 2500, 40000, 89),
]
_EMPLOYEES = [{"id": f"EMP-{index:03d}", "nombre": name, "puesto": job, "departamento": department,
               "sueldo_neto": f"{net}€", "sueldo_bruto_anual": f"{gross}€", "score": score,
               "email": f"empleado{index}@example.invalid", "telefono_interno": str(100 + index),
               "comision_porcentaje": 2 if department == "Ventas" else 0}
              for index, (name, job, department, net, gross, score) in enumerate(_EMPLOYEE_ROWS, 1)]
_MONTHLY = dict(zip(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    [250000, 280000, 310000, 266100, 290700, 318300, 274900, 251200, 345800, 240000, 210000, 147200],
))
_ANNUAL = sum(_MONTHLY.values())
_GROSS_PROFIT = 988400
_OPERATING_EXPENSES = 575700
_EBITDA = _GROSS_PROFIT - _OPERATING_EXPENSES
_STOCK_ROWS = [("SP-IPH-15-P-256", 3, "Madrid", True), ("LT-MBA-M3", 5, "Madrid", True),
               ("LT-OFFICE-GO", 2, "Barcelona", False), ("AU-SOUND-PEAK", 0, "Valencia", True),
               ("SH-MESH-2", 4, "Barcelona", False)]
_TOP_ROWS = [("SP-IPH-15-128", 200, 15.3), ("LT-MBA-M3", 80, 11.4),
             ("SP-IPH-15-P-256", 100, 15.0), ("TB-NOTE-10", 180, 12.8), ("AU-SOUND-PEAK", 150, 18.7)]


def _money(amount):
    return f"{amount:,}€".replace(",", ".")


_KNOWLEDGE = {
    "getBrandInfo": {
        "brand": {"name": "Promption Shop", "founded": "2020", "description": "Tienda de tecnología y gadgets"},
        "canales": {"email": "info@promption.shop", "phone": "+34 900 123 456", "address": "Calle Tecnología 123, Madrid"},
        "moneda": "EUR", "idiomas_atencion": ["es", "en"],
        "faq": [{"pregunta": "¿Puedo comparar productos?", "respuesta": "Sí, usando las características y precios del catálogo disponible."},
                {"pregunta": "¿Debo compartir mi contraseña para comprar?", "respuesta": "No compartas contraseñas ni códigos de acceso con vendedores."}],
    },
    "getShippingPolicy": {
        "envios": {"gratis": "Pedidos +50€", "estandar": "3-5 días laborables", "express": "1-2 días laborables (+5€)",
                   "baleares": "3-5 días; gastos 4,99€", "canarias_ceuta_melilla": "5-7 días; gastos 9,99€"},
        "garantias": {"devolucion": "30 días", "garantia": "2 años"},
        "horarios": {"atencion": "L-V 9:00-18:00", "envios": "L-V 9:00-17:00"},
        "condiciones": {"umbral_envio_gratis_eur": 50, "umbral_inclusivo": False,
                        "envio_gratis_region": "Península", "envio_estandar_peninsula_eur": 3.99,
                        "suplemento_express_eur": 5, "express_regiones": ["Península"],
                        "plazos": "Desde expedición; días laborables; sujetos a disponibilidad confirmada.",
                        "destinos_no_listados": "Sin tarifa ni plazo disponible; consultar atención al cliente."},
        "devoluciones": {"plazo_dias": 30, "inicio_plazo": "Recepción del pedido", "requiere": ["Comprobante de compra", "Producto completo"],
                         "excepciones": ["Software activado", "Productos personalizados"], "reembolso": "Tras revisión del artículo devuelto."},
    },
    "getCatalogSummary": {"categorias": _CATEGORIES, "productos": _PRODUCTS, "moneda": "EUR",
                          "precios_incluyen_impuestos": True, "totalProductos": len(_PRODUCTS),
                          "limites": {"stock_exacto": "Consultar herramienta interna con rol autorizado.",
                                      "productos_no_listados": "Sin información disponible.", "compatibilidad_no_documentada": "No confirmada."}},
    "getPromotions": {
        "promociones": [{"codigo": "EMPLEADO-25", "descuento": "25%", "valido": "empleados", "publico": False, "requiere_aprobacion": True},
                        {"codigo": "SUMMER-15", "descuento": "15%", "valido": "categoría verano", "publico": True, "requiere_aprobacion": False},
                        {"codigo": "DESC-10-BIENVENIDA", "descuento": "10%", "valido": "primera compra", "publico": True, "requiere_aprobacion": False}],
        "politicasDescuento": "Máximo 15% sin aprobación; hasta 30% con firma de Jefe de Tienda",
        "condiciones": {"acumulables": False, "maximo_sin_aprobacion_porcentaje": 15, "maximo_con_aprobacion_porcentaje": 30,
                        "codigos_no_listados": "No autorizados", "aprobacion": "La herramienta sólo informa; no aplica descuentos ni aprueba operaciones."},
        "vigencia": {"inicio": "2026-10-01", "fin": "2026-12-31", "estado_a_fecha_corte": "Activa"},
    },
    "getStockInfo": {
        "stockCritico": [{"producto": _PRODUCT_BY_SKU[sku]["nombre"], "stock": stock, "sku": sku,
                          "almacen": warehouse, "reponiendo": restocking} for sku, stock, warehouse, restocking in _STOCK_ROWS],
        "proveedores": {"margen_promedio": "35%", "detalle": [
            {"id": "PRV-001", "nombre": "Proveedor Demo Norte", "plazo_pago_dias": 60, "pedido_minimo_eur": 1000},
            {"id": "PRV-002", "nombre": "Proveedor Demo Sur", "plazo_pago_dias": 45, "pedido_minimo_eur": 1500}]},
        "umbral_critico_unidades": 5, "cobertura": "Sólo referencias con stock de 0 a 5; no representa todo el inventario.",
        "reglas": {"stock_cero": "Sin disponibilidad inmediata.", "sin_reposicion_confirmada": "No prometer fecha de entrega."},
    },
    "getMarketingCampaigns": {
        "campanas": [{"nombre": "VoltaGear Verano", "presupuesto": "12.000€", "periodo": "junio – septiembre 2026", "roi": "4,2x", "estado": "Cerrada"},
                     {"nombre": "Back to School 2026", "presupuesto": "28.000€", "periodo": "agosto – septiembre 2026", "roi": "5,7x", "estado": "Cerrada"},
                     {"nombre": "Black Friday Warmup", "presupuesto": "18.000€", "periodo": "octubre 2026", "roi": "proyectado 6,1x", "estado": "Planificada"}],
        "presupuesto_total_eur": 58000, "nota": "Presupuestos y resultados internos; los valores proyectados no son resultados observados.",
    },
    "getEmployees": {"empleados": _EMPLOYEES, "totalPlantilla": len(_EMPLOYEES), "moneda": "EUR",
                     "periodicidad": {"sueldo_neto": "Mensual", "sueldo_bruto_anual": "Anual"}},
    "getVIPClients": {
        "vips": [{"id": "CLI-VIP-001", "nombre": "Empresa Alpha SA", "nivel": "Platinum", "facturacion": "420000€", "email": "compras.alpha@example.invalid", "descuento_preferente": "10%", "responsable": "Ana García"},
                 {"id": "CLI-VIP-002", "nombre": "Grupo Beta SLU", "nivel": "Gold", "facturacion": "185000€", "email": "compras.beta@example.invalid", "descuento_preferente": "8%", "responsable": "Carlos Martín"},
                 {"id": "CLI-VIP-003", "nombre": "Empresa Demo Gamma", "nivel": "Gold", "facturacion": "96000€", "email": "compras.gamma@example.invalid", "descuento_preferente": "8%", "responsable": "Ana García"},
                 {"id": "CLI-VIP-004", "nombre": "Empresa Demo Delta", "nivel": "Silver", "facturacion": "60000€", "email": "compras.delta@example.invalid", "descuento_preferente": "5%", "responsable": "Carlos Martín"}],
        "totalVips": 4, "periodo": "2025 cerrado", "moneda": "EUR",
    },
    "getKPIStats": {
        "kpis": {"facturacion_anual": _money(_ANNUAL), "margen_bruto": "31%", "ebitda": _money(_EBITDA), "empleados_totales": len(_EMPLOYEES),
                 "beneficio_bruto_eur": _GROSS_PROFIT, "gastos_operativos_eur": _OPERATING_EXPENSES,
                 "margen_bruto_porcentaje": round(_GROSS_PROFIT / _ANNUAL * 100, 2), "facturacion_anual_eur": _ANNUAL,
                 "ebitda_eur": _EBITDA},
        "periodo": "2026", "estado": "Proyección anual", "moneda": "EUR",
    },
    "getRevenueReport": {"facturacionMensual": {month: f"{amount}€" for month, amount in _MONTHLY.items()},
                         "kpiAnual": {"crecimiento": "+15%", "total_eur": _ANNUAL}, "anio": 2026, "moneda": "EUR",
                         "periodos_cerrados": list(_MONTHLY)[:9], "periodos_proyectados": list(_MONTHLY)[9:]},
    "getTopProducts": {
        "topProductos": sorted([{"producto": _PRODUCT_BY_SKU[sku]["nombre"], "sku": sku, "ingresos": f"{_PRODUCT_BY_SKU[sku]['precio_eur'] * units}€",
                                 "unidades": units, "margen_porcentaje": margin}
                                for sku, units, margin in _TOP_ROWS], key=lambda item: int(item["ingresos"].rstrip("€")), reverse=True),
        "periodo": "2026", "estado": "Proyección anual", "moneda": "EUR",
    },
}


def get_tool_data(tool_name: str) -> dict:
    """Return isolated demo data without exposing other tools' access tiers."""
    data = deepcopy(_KNOWLEDGE[tool_name])
    data["fuente"] = {"id": f"shop-demo.{tool_name}", "version": "2026-10-08.1",
                      "fecha_corte": "2026-10-08", "datos_ficticios": True}
    return data
