"""Shop handlers and access rules consumed by the Promption MCP library."""
from typing import Any, List, Optional
from .lib.shop_knowledge import get_tool_data
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
                handler=self._get_brand_info,
                guest_read=True,
            ),
            ToolPolicy(
                name="getShippingPolicy",
                description="Políticas públicas de envío, devoluciones, garantías y horarios.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                handler=self._get_shipping_policy,
                guest_read=True,
            ),
            ToolPolicy(
                name="getCatalogSummary",
                description="Categorías, productos, SKU, precios y características públicas del catálogo de la tienda.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                handler=self._get_catalog_summary,
                guest_read=True,
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
                description="Informe mensual 2026, con periodos cerrados y proyectados identificados, y crecimiento. TIER CONFIDENCIAL. SÓLO admin.",
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
        return get_tool_data("getBrandInfo")

    def _get_shipping_policy(self) -> dict[str, Any]:
        return get_tool_data("getShippingPolicy")

    def _get_catalog_summary(self) -> dict[str, Any]:
        return get_tool_data("getCatalogSummary")

    def _get_promotions(self) -> dict[str, Any]:
        return get_tool_data("getPromotions")

    def _get_stock_info(self) -> dict[str, Any]:
        return get_tool_data("getStockInfo")

    def _get_marketing_campaigns(self) -> dict[str, Any]:
        return get_tool_data("getMarketingCampaigns")

    def _get_employees(self) -> dict[str, Any]:
        return get_tool_data("getEmployees")

    def _get_vip_clients(self) -> dict[str, Any]:
        return get_tool_data("getVIPClients")

    def _get_kpi_stats(self) -> dict[str, Any]:
        return get_tool_data("getKPIStats")

    def _get_revenue_report(self) -> dict[str, Any]:
        return get_tool_data("getRevenueReport")

    def _get_top_products(self) -> dict[str, Any]:
        return get_tool_data("getTopProducts")

_mcp_executor: Optional[MCPToolExecutor] = None


def get_mcp_executor() -> MCPToolExecutor:
    global _mcp_executor
    if _mcp_executor is None:
        _mcp_executor = MCPToolExecutor()
    return _mcp_executor
