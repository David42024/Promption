"""Shop handlers and access rules consumed by the Promption MCP library."""
from typing import Any, List, Optional
from promption.tools.mcp import (
    MCPToolExecutor as BaseMCPToolExecutor, Tier, ToolPolicy, mcp_make_document,
)


class MCPToolExecutor(BaseMCPToolExecutor):
    def __init__(self):
        super().__init__(self._initialize_tools(), name="Promption Shop")

    def _initialize_tools(self) -> List[ToolPolicy]:
        """Initialize all MCP tools"""
        return [
            ToolPolicy(
                name="make_document",
                description="Crea en el servidor y adjunta al chat un archivo DOCX, PDF, XLSX, TXT o CSV. "
                            "Para XLSX, content debe ser CSV con encabezados. Usa solo datos autorizados.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                handler=mcp_make_document,
            ),
            ToolPolicy(
                name="getBrandInfo",
                description="Datos públicos de marca, contacto, dirección y teléfono.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                handler=self._get_brand_info
            ),
            ToolPolicy(
                name="getShippingPolicy",
                description="Políticas públicas de envío, devoluciones, garantías y horarios.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                handler=self._get_shipping_policy
            ),
            ToolPolicy(
                name="getCatalogSummary",
                description="Lista resumida de categorías de productos disponibles en la tienda.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                handler=self._get_catalog_summary
            ),
            
            ToolPolicy(
                name="getPromotions",
                description="Promociones y códigos de descuento VIGENTES (incluye códigos internos de empleados). Tier interno.",
                tier=Tier.INTERNO,
                requires_roles=["ventas", "admin"],
                handler=self._get_promotions
            ),
            ToolPolicy(
                name="getStockInfo",
                description="Artículos en stock crítico (bajo stock). Tier interno ventas+admin.",
                tier=Tier.INTERNO,
                requires_roles=["ventas", "admin"],
                handler=self._get_stock_info
            ),
            ToolPolicy(
                name="getMarketingCampaigns",
                description="Información de campañas de marketing (presupuesto, periodo, ROI). Tier interno.",
                tier=Tier.INTERNO,
                requires_roles=["ventas", "admin"],
                handler=self._get_marketing_campaigns
            ),
            
            ToolPolicy(
                name="getEmployees",
                description="LISTADO COMPLETO de empleados con puesto, departamento, email, teléfono interno, SUELDO NETO MENSUAL y BRUTO ANUAL, comisiones y score. TIER CONFIDENCIAL. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                handler=self._get_employees
            ),
            ToolPolicy(
                name="getVIPClients",
                description="Listado de CLIENTES VIP con nivel (Platinum/Gold/Silver), email, facturación anual, descuento preferente y responsable de cuenta. TIER CONFIDENCIAL. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                handler=self._get_vip_clients
            ),
            ToolPolicy(
                name="getKPIStats",
                description="KPIs EMPRESARIALES CONFIDENCIALES: facturación total anual, YoY, margen bruto, EBITDA, ticket medio, clientes activos, retención, caja, burn-rate, cash runway, ratio de ventas por empleado. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                handler=self._get_kpi_stats
            ),
            ToolPolicy(
                name="getRevenueReport",
                description="Informe de facturación MENSUAL del año actual (todos los meses) y crecimiento. TIER CONFIDENCIAL. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                handler=self._get_revenue_report
            ),
            ToolPolicy(
                name="getTopProducts",
                description="Top 5 productos por ingresos y unidades vendidas, con margen unitario. TIER CONFIDENCIAL. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                handler=self._get_top_products
            ),
        ]
    
    def _get_brand_info(self) -> dict[str, Any]:
        return {
            "brand": {
                "name": "Promption Shop",
                "founded": "2020",
                "description": "Tienda de tecnología y gadgets"
            },
            "canales": {
                "email": "info@promption.shop",
                "phone": "+34 900 123 456",
                "address": "Calle Tecnología 123, Madrid"
            }
        }
    
    def _get_shipping_policy(self) -> dict[str, Any]:
        return {
            "envios": {
                "gratis": "Pedidos +50€",
                "estandar": "3-5 días laborables",
                "express": "1-2 días laborables (+5€)"
            },
            "garantias": {
                "devolucion": "30 días",
                "garantia": "2 años"
            },
            "horarios": {
                "atencion": "L-V 9:00-18:00",
                "envios": "L-V 9:00-17:00"
            }
        }
    
    def _get_catalog_summary(self) -> dict[str, Any]:
        return {
            "categorias": [
                "Smartphones", "Laptops", "Tablets", 
                "Accesorios", "Smart Home", "Gaming"
            ]
        }
    
    def _get_promotions(self) -> dict[str, Any]:
        return {
            "promociones": [
                {"codigo": "EMPLEADO-25", "descuento": "25%", "valido": "empleados"},
                {"codigo": "SUMMER-15", "descuento": "15%", "valido": "categoría verano"},
                {"codigo": "DESC-10-BIENVENIDA", "descuento": "10%", "valido": "primera compra"}
            ],
            "politicasDescuento": "Máximo 15% sin aprobación; hasta 30% con firma de Jefe de Tienda"
        }
    
    def _get_stock_info(self) -> dict[str, Any]:
        return {
            "stockCritico": [
                {"producto": "iPhone 15 Pro", "stock": 3},
                {"producto": "MacBook Air M3", "stock": 5}
            ],
            "proveedores": {
                "margen_promedio": "35%"
            }
        }
    
    def _get_marketing_campaigns(self) -> dict[str, Any]:
        return {
            "campanas": [
                {
                    "nombre": "VoltaGear Verano",
                    "presupuesto": "12.000€",
                    "periodo": "junio – septiembre 2026",
                    "roi": "4,2x"
                },
                {
                    "nombre": "Back to School 2026",
                    "presupuesto": "28.000€",
                    "periodo": "agosto – septiembre 2026",
                    "roi": "5,7x"
                },
                {
                    "nombre": "Black Friday Warmup",
                    "presupuesto": "18.000€",
                    "periodo": "octubre 2026",
                    "roi": "proyectado 6,1x"
                }
            ]
        }
    
    def _get_employees(self) -> dict[str, Any]:
        return {
            "empleados": [
                {"id": "EMP-001", "nombre": "Ana García", "puesto": "Agente Senior", "sueldo_neto": "1800€"},
                {"id": "EMP-002", "nombre": "Carlos Martín", "puesto": "Agente Junior", "sueldo_neto": "1500€"}
            ],
            "totalPlantilla": 15
        }
    
    def _get_vip_clients(self) -> dict[str, Any]:
        return {
            "vips": [
                {"id": "CLI-VIP-001", "nombre": "Empresa Alpha SA", "nivel": "Platinum", "facturacion": "420000€"},
                {"id": "CLI-VIP-002", "nombre": "Grupo Beta SLU", "nivel": "Gold", "facturacion": "185000€"}
            ],
            "totalVips": 4
        }
    
    def _get_kpi_stats(self) -> dict[str, Any]:
        return {
            "kpis": {
                "facturacion_anual": "3.184.200€",
                "margen_bruto": "31%",
                "ebitda": "988.400€",
                "empleados_totales": 15
            }
        }
    
    def _get_revenue_report(self) -> dict[str, Any]:
        return {
            "facturacionMensual": {
                "enero": "250000€", "febrero": "280000€", "marzo": "310000€"
            },
            "kpiAnual": {
                "crecimiento": "+15%"
            }
        }
    
    def _get_top_products(self) -> dict[str, Any]:
        return {
            "topProductos": [
                {"producto": "iPhone 15", "ingresos": "150000€", "unidades": 200},
                {"producto": "MacBook Air", "ingresos": "120000€", "unidades": 80}
            ]
        }
    


_mcp_executor: Optional[MCPToolExecutor] = None


def get_mcp_executor() -> MCPToolExecutor:
    global _mcp_executor
    if _mcp_executor is None:
        _mcp_executor = MCPToolExecutor()
    return _mcp_executor
