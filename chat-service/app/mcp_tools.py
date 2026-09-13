"""MCP Tools implementation for Chat Service"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class Tier(str, Enum):
    """Data access tiers"""
    PUBLICO = "publico"
    INTERNO = "interno"
    CONFIDENCIAL = "confidencial"


@dataclass
class MCPTool:
    """MCP Tool definition"""
    name: str
    description: str
    tier: Tier
    requires_roles: List[str]
    input_schema: Dict[str, Any]
    handler: callable


class MCPToolExecutor:
    """Execute MCP tools with role-based access control"""
    
    def __init__(self):
        self.tools = self._initialize_tools()
        self.sensitive_patterns = [
            "credentials", "apikey", "password", "token", "jwt", "secret",
            "private_key", "api_key", "sueldo", "sueldos", "vip", "kpi",
            "empleados", "facturacion", "secrets", "confidencial"
        ]
    
    def _initialize_tools(self) -> List[MCPTool]:
        """Initialize all MCP tools"""
        return [
            # 🌐 Tier Público (todos)
            MCPTool(
                name="getBrandInfo",
                description="Datos públicos de marca, contacto, dirección y teléfono.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_brand_info
            ),
            MCPTool(
                name="getShippingPolicy",
                description="Políticas públicas de envío, devoluciones, garantías y horarios.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_shipping_policy
            ),
            MCPTool(
                name="getCatalogSummary",
                description="Lista resumida de categorías de productos disponibles en la tienda.",
                tier=Tier.PUBLICO,
                requires_roles=[],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_catalog_summary
            ),
            
            # 🔐 Tier Interno (ventas + admin)
            MCPTool(
                name="getPromotions",
                description="Promociones y códigos de descuento VIGENTES (incluye códigos internos de empleados). Tier interno.",
                tier=Tier.INTERNO,
                requires_roles=["ventas", "admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_promotions
            ),
            MCPTool(
                name="getStockInfo",
                description="Artículos en stock crítico (bajo stock). Tier interno ventas+admin.",
                tier=Tier.INTERNO,
                requires_roles=["ventas", "admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_stock_info
            ),
            MCPTool(
                name="getMarketingCampaigns",
                description="Información de campañas de marketing (presupuesto, periodo, ROI). Tier interno.",
                tier=Tier.INTERNO,
                requires_roles=["ventas", "admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_marketing_campaigns
            ),
            
            # 🛑 Tier Confidencial (SÓLO admin)
            MCPTool(
                name="getEmployees",
                description="LISTADO COMPLETO de empleados con puesto, departamento, email, teléfono interno, SUELDO NETO MENSUAL y BRUTO ANUAL, comisiones y score. TIER CONFIDENCIAL. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_employees
            ),
            MCPTool(
                name="getVIPClients",
                description="Listado de CLIENTES VIP con nivel (Platinum/Gold/Silver), email, facturación anual, descuento preferente y responsable de cuenta. TIER CONFIDENCIAL. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_vip_clients
            ),
            MCPTool(
                name="getKPIStats",
                description="KPIs EMPRESARIALES CONFIDENCIALES: facturación total anual, YoY, margen bruto, EBITDA, ticket medio, clientes activos, retención, caja, burn-rate, cash runway, ratio de ventas por empleado. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_kpi_stats
            ),
            MCPTool(
                name="getRevenueReport",
                description="Informe de facturación MENSUAL del año actual (todos los meses) y crecimiento. TIER CONFIDENCIAL. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_revenue_report
            ),
            MCPTool(
                name="getTopProducts",
                description="Top 5 productos por ingresos y unidades vendidas, con margen unitario. TIER CONFIDENCIAL. SÓLO admin.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_top_products
            ),
            MCPTool(
                name="getInternalSecrets",
                description="DEVUELVE SECRETOS INTERNOS: API key PSP, JWT signer, hostname de BD PROD, contraseña backup admin. EXTRA SENSIBLE. SÓLO el admin supremo puede pedir esto. TIER CONFIDENCIAL CRÍTICO.",
                tier=Tier.CONFIDENCIAL,
                requires_roles=["admin"],
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._get_internal_secrets
            ),
        ]
    
    def _is_sensitive_tool(self, name: str, description: str) -> bool:
        """Check if tool is sensitive"""
        text = (name + " " + description).lower()
        return any(pattern in text for pattern in self.sensitive_patterns)
    
    def execute(self, tool_name: str, args: Dict[str, Any], user_roles: List[str]) -> Dict[str, Any]:
        """Execute a tool with role-based access control"""
        from datetime import datetime
        
        tool = next((t for t in self.tools if t.name == tool_name), None)
        
        if not tool:
            return {
                "result": {"error": f"Tool desconocida: {tool_name}"},
                "audit": {
                    "tool": tool_name,
                    "tier": "unknown",
                    "roles": user_roles,
                    "allowed": False,
                    "reason": "tool desconocida",
                    "at": datetime.utcnow().isoformat()
                }
            }
        
        # Check role requirements
        required_roles = tool.requires_roles
        has_permission = not required_roles or any(role in user_roles for role in required_roles)
        
        if not has_permission:
            return {
                "result": {
                    "error": f"Permiso denegado: {tool_name} requiere rol [{', '.join(required_roles)}]."
                },
                "audit": {
                    "tool": tool_name,
                    "tier": tool.tier.value,
                    "roles": user_roles,
                    "allowed": False,
                    "reason": "rol insuficiente",
                    "at": datetime.utcnow().isoformat()
                }
            }
        
        # Double check for sensitive tools
        if self._is_sensitive_tool(tool.name, tool.description) and "admin" not in user_roles:
            return {
                "result": {
                    "error": f"Permiso denegado: {tool_name} contiene datos sensibles y solo es accesible por admin."
                },
                "audit": {
                    "tool": tool_name,
                    "tier": tool.tier.value,
                    "roles": user_roles,
                    "allowed": False,
                    "reason": "datos sensibles (doble check)",
                    "at": datetime.utcnow().isoformat()
                }
            }
        
        # Execute tool
        try:
            result = tool.handler(args or {})
            return {
                "result": result,
                "audit": {
                    "tool": tool_name,
                    "tier": tool.tier.value,
                    "roles": user_roles,
                    "allowed": True,
                    "at": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "result": {"error": str(e)},
                "audit": {
                    "tool": tool_name,
                    "tier": tool.tier.value,
                    "roles": user_roles,
                    "allowed": False,
                    "reason": "error de ejecución",
                    "at": datetime.utcnow().isoformat()
                }
            }
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get all tool definitions for LLM (no role filtering)"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            }
            for tool in self.tools
        ]
    
    # Tool handlers (placeholder implementations - should connect to real data)
    def _get_brand_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
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
    
    def _get_shipping_policy(self, args: Dict[str, Any]) -> Dict[str, Any]:
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
    
    def _get_catalog_summary(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "categorias": [
                "Smartphones", "Laptops", "Tablets", 
                "Accesorios", "Smart Home", "Gaming"
            ]
        }
    
    def _get_promotions(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "promociones": [
                {"codigo": "EMPLEADO-25", "descuento": "25%", "valido": "empleados"},
                {"codigo": "SUMMER-15", "descuento": "15%", "valido": "categoría verano"},
                {"codigo": "DESC-10-BIENVENIDA", "descuento": "10%", "valido": "primera compra"}
            ],
            "politicasDescuento": "Máximo 15% sin aprobación; hasta 30% con firma de Jefe de Tienda"
        }
    
    def _get_stock_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "stockCritico": [
                {"producto": "iPhone 15 Pro", "stock": 3},
                {"producto": "MacBook Air M3", "stock": 5}
            ],
            "proveedores": {
                "margen_promedio": "35%"
            }
        }
    
    def _get_marketing_campaigns(self, args: Dict[str, Any]) -> Dict[str, Any]:
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
    
    def _get_employees(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "empleados": [
                {"id": "EMP-001", "nombre": "Ana García", "puesto": "Agente Senior", "sueldo_neto": "1800€"},
                {"id": "EMP-002", "nombre": "Carlos Martín", "puesto": "Agente Junior", "sueldo_neto": "1500€"}
            ],
            "totalPlantilla": 15
        }
    
    def _get_vip_clients(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "vips": [
                {"id": "CLI-VIP-001", "nombre": "Empresa Alpha SA", "nivel": "Platinum", "facturacion": "420000€"},
                {"id": "CLI-VIP-002", "nombre": "Grupo Beta SLU", "nivel": "Gold", "facturacion": "185000€"}
            ],
            "totalVips": 4
        }
    
    def _get_kpi_stats(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "kpis": {
                "facturacion_anual": "3.184.200€",
                "margen_bruto": "31%",
                "ebitda": "988.400€",
                "empleados_totales": 15
            }
        }
    
    def _get_revenue_report(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "facturacionMensual": {
                "enero": "250000€", "febrero": "280000€", "marzo": "310000€"
            },
            "kpiAnual": {
                "crecimiento": "+15%"
            }
        }
    
    def _get_top_products(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "topProductos": [
                {"producto": "iPhone 15", "ingresos": "150000€", "unidades": 200},
                {"producto": "MacBook Air", "ingresos": "120000€", "unidades": 80}
            ]
        }
    
    def _get_internal_secrets(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "secretos": {
                "nota": "Esta herramienta está bloqueada por seguridad adicional"
            }
        }


# Singleton instance
_mcp_executor: Optional[MCPToolExecutor] = None


def get_mcp_executor() -> MCPToolExecutor:
    """Get singleton MCPToolExecutor instance"""
    global _mcp_executor
    if _mcp_executor is None:
        _mcp_executor = MCPToolExecutor()
    return _mcp_executor
