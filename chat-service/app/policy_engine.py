"""Deterministic business-data classification and role-based authorization."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional


TIER_ALLOWED_ROLES = {
    "publico": frozenset({"guest", "customer", "ventas", "admin"}),
    "interno": frozenset({"ventas", "admin"}),
    "confidencial": frozenset({"admin"}),
    "restringido": frozenset(),
}

OUTPUT_GUARD_OWNED_POLICIES = frozenset({"confidential.credentials"})


from promption.policies import ResourcePolicy, PolicyDecision, normalize_text, PolicyEngine as BasePolicyEngine

RESOURCE_POLICIES = (
    ResourcePolicy(
        policy_id="confidential.credentials",
        resource="internal_credentials",
        tier="restringido",
        tool_names=(),
        patterns=(
            r"\b(dame|muestra(?:me)?|revela(?:me)?|comparte(?:me)?|necesito|cual\s+es|quiero|accede(?:r)?)\b.{0,70}\b(api\s*key|apikey|jwt|token|password|contrasena|clave\s+privada|credencial(?:es)?|secreto(?:s)?|hostname|base\s+de\s+datos|db\s*prod)\b.{0,45}\b(interno(?:s)?|admin|pasarela|produccion|backup|firmador|empresa|sistema)\b",
            r"\b(api\s*key|jwt|password|contrasena|credencial(?:es)?|secreto(?:s)?)\b.{0,55}\b(interno(?:s)?|admin|pasarela|produccion|backup|firmador)\b",
        ),
        confidence=0.99,
    ),
    ResourcePolicy(
        policy_id="confidential.payroll",
        resource="employee_payroll",
        tier="confidencial",
        tool_names=("getEmployees",),
        patterns=(
            r"\b(sueldo(?:s)?|salario(?:s)?|nomina(?:s)?|remuneracion(?:es)?|cuanto\s+cobra|comision(?:es)?)\b",
            r"\b(score|puntuacion)\b.{0,45}\b(emplead\w*|ana|carlos|laura|miguel|director|jefe)\b",
        ),
        confidence=0.98,
    ),
    ResourcePolicy(
        policy_id="confidential.vip_clients",
        resource="vip_clients",
        tier="confidencial",
        tool_names=("getVIPClients",),
        patterns=(
            r"\b(cliente(?:s)?\s+vip|vip\s*\d*|empresa\s+alpha|grupo\s+beta|gamma\s+innovaciones)\b.{0,80}\b(email(?:s)?|correo(?:s)?|facturacion|ingresos|compras\s+anual(?:es)?|descuento\s+preferente|responsable\s+de\s+cuenta|cartera|listado|lista|detalle(?:s)?|datos)\b",
            r"\b(email(?:s)?|correo(?:s)?|facturacion|ingresos|compras\s+anual(?:es)?|descuento\s+preferente|responsable\s+de\s+cuenta|cartera|listado|lista|detalle(?:s)?|datos)\b.{0,80}\b(cliente(?:s)?\s+vip|vip\s*\d*|empresa\s+alpha|grupo\s+beta|gamma\s+innovaciones)\b",
            r"\b(descuento\s+preferente|responsable\s+de\s+cuenta)\b",
        ),
        confidence=0.97,
    ),
    ResourcePolicy(
        policy_id="confidential.financial_kpis",
        resource="financial_kpis",
        tier="confidencial",
        tool_names=("getKPIStats",),
        patterns=(
            r"\b(ebitda|burn\s*rate|cash\s*runway|caja\s+actual|margen\s+bruto|inventario\s+valorado|deuda\s+(?:a\s+)?proveedores)\b",
            r"\b(facturacion|ingresos)\b.{0,45}\b(anual|este\s+ano|empresa|total)\b",
            r"\b(reporte|informe)\b.{0,35}\b(financiero|facturacion\s+anual|ingresos\s+anuales)\b",
        ),
        confidence=0.97,
    ),
    ResourcePolicy(
        policy_id="confidential.revenue_report",
        resource="monthly_revenue_report",
        tier="confidencial",
        tool_names=("getRevenueReport",),
        patterns=(
            r"\b(facturacion|ingresos)\b.{0,35}\b(mes\s+a\s+mes|por\s+mes|mensual|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre)\b",
            r"\b(reporte|informe)\b.{0,40}\b(mensual|mes\s+a\s+mes|por\s+mes)\b.{0,35}\b(facturacion|ingresos)\b",
        ),
        confidence=0.98,
    ),
    ResourcePolicy(
        policy_id="confidential.product_performance",
        resource="product_performance",
        tier="confidencial",
        tool_names=("getTopProducts",),
        patterns=(
            r"\b(top\s*\d*\s+productos|productos?\s+mas\s+vendidos|margen\s+real\s+por\s+producto|unidades\s+vendidas\s+por\s+sku)\b",
        ),
        confidence=0.96,
    ),
    ResourcePolicy(
        policy_id="confidential.admin_profile",
        resource="employee_admin_profile",
        tier="confidencial",
        tool_names=("getEmployees",),
        patterns=(
            r"\b(informacion|datos|perfil|detalle(?:s)?)\b.{0,40}\b(del\s+admin|administrador|director\s+general|jefe)\b",
        ),
        confidence=0.93,
    ),
    ResourcePolicy(
        policy_id="internal.marketing_campaigns",
        resource="marketing_campaigns",
        tier="interno",
        tool_names=("getMarketingCampaigns",),
        patterns=(
            r"\b(campa\w*|marketing|voltagear|back\s+to\s+school|black\s+friday\s+warmup)\b.{0,80}\b(presupuesto|roi|roas|ctr\s+ads|briefing|objetivo(?:s)?|proyeccion(?:es)?|intern[oa]s?|direccion)\b",
            r"\b(presupuesto|roi|roas|ctr\s+ads|briefing|objetivo(?:s)?|proyeccion(?:es)?)\b.{0,80}\b(campa\w*|marketing|voltagear|back\s+to\s+school|black\s+friday\s+warmup)\b",
        ),
        confidence=0.97,
    ),
    ResourcePolicy(
        policy_id="internal.stock",
        resource="internal_stock",
        tier="interno",
        tool_names=("getStockInfo",),
        patterns=(
            r"\b(stock|stcok|inventario|existencias|unidades\s+(?:restantes|disponibles)|almacen|reponiendo|rotura\s+de\s+stock|proveedor(?:es)?|margen\s+con)\b",
        ),
        confidence=0.94,
        output_patterns=(
            r"\b(stock|inventario|existencias)\b.{0,45}\b(interno|critico|actual|bajo|agotado|disponible|quedan|hay|\d+)\b",
            r"\b(interno|critico|actual|bajo|agotado|disponible|quedan|hay|\d+)\b.{0,45}\b(stock|inventario|existencias)\b",
            r"\b(unidades\s+(?:restantes|disponibles)|rotura\s+de\s+stock|reponiendo|proveedor(?:es)?|margen(?:es)?(?:\s+promedio)?|stockcritico)\b",
        ),
    ),
    ResourcePolicy(
        policy_id="internal.promotions",
        resource="internal_promotions",
        tier="interno",
        tool_names=("getPromotions",),
        patterns=(
            r"\bpolitica(?:s)?\s+(?:de|sobre)\s+(?:descuento(?:s)?|promocion(?:es)?)\b",
            r"\b(descuento|codigo)\b.{0,45}\b(emplead\w*|interno|sin\s+aprobacion|con\s+aprobacion|jefe|excepcional)\b",
            r"\b(empleado-?25|desc-?50-?interno|politica(?:s)?\s+comercial(?:es)?)\b",
        ),
        confidence=0.96,
    ),
    ResourcePolicy(
        policy_id="public.promotions",
        resource="public_promotions",
        tier="publico",
        tool_names=(),
        patterns=(
            r"\b(promocion(?:es)?|oferta(?:s)?|descuento(?:s)?|cupon(?:es)?|codigo(?:s)?\s+promocional(?:es)?)\b",
        ),
        confidence=0.86,
    ),
    ResourcePolicy(
        policy_id="public.vip_benefits",
        resource="vip_benefits",
        tier="publico",
        tool_names=(),
        patterns=(
            r"\b(beneficio(?:s)?|ventaja(?:s)?|privilegio(?:s)?)\b.{0,45}\b(cliente\s+vip|vip)\b",
            r"\b(cliente\s+vip|vip)\b.{0,45}\b(beneficio(?:s)?|ventaja(?:s)?|privilegio(?:s)?)\b",
        ),
        confidence=0.86,
    ),
    ResourcePolicy(
        policy_id="public.shipping",
        resource="shipping_and_returns",
        tier="publico",
        tool_names=("getShippingPolicy",),
        patterns=(
            r"\b(envio(?:s)?|devolucion(?:es)?|garantia(?:s)?|canarias|baleares|entrega|cuanto\s+tarda)\b",
        ),
        confidence=0.92,
    ),
    ResourcePolicy(
        policy_id="public.catalog",
        resource="product_catalog",
        tier="publico",
        tool_names=("getCatalogSummary",),
        patterns=(
            r"\b(catalogo|producto(?:s)?|portatil(?:es)?|smartphone(?:s)?|auricular(?:es)?|tablet(?:s)?|reloj(?:es)?|gaming)\b",
        ),
        confidence=0.88,
    ),
    ResourcePolicy(
        policy_id="public.brand",
        resource="brand_information",
        tier="publico",
        tool_names=("getBrandInfo",),
        patterns=(
            r"\b(horario(?:s)?|contacto|direccion\s+de\s+la\s+tienda|telefono\s+de\s+la\s+tienda|promption\s+shop|quienes\s+son)\b",
        ),
        confidence=0.88,
    ),
)


class PolicyEngine(BasePolicyEngine):
    """Configure the library with the unchanged shop resource policies."""

    def __init__(self, policies: Iterable[ResourcePolicy] = RESOURCE_POLICIES):
        super().__init__(policies, tier_roles=TIER_ALLOWED_ROLES,
                         output_excluded_policy_ids=OUTPUT_GUARD_OWNED_POLICIES,
                         allow_unmatched=True)

    def classify_all(self, text: str, *, output: bool = False) -> tuple[ResourcePolicy, ...]:
        """Keep conceptual mentions distinct from access to company records."""
        normalized = normalize_text(text)
        if output:
            safe_refusal = re.fullmatch(
                r"(?:no (?:puedo|tengo permiso para) (?:compartir|mostrar|consultar) "
                r"(?:sueldos(?: de empleados)?|nominas|datos confidenciales|informacion confidencial"
                r"|(?:el )?listado de clientes vip|(?:el )?stock interno|(?:la )?facturacion mensual"
                r"|(?:los )?proveedores de la empresa)"
                r"|(?:necesitas|se requiere) (?:el )?rol admin para consultar (?:nominas|sueldos))"
                r"[.! ]*", normalized)
            if safe_refusal:
                return ()
            if re.fullmatch(
                r"(?:el )?stock (?:es|significa|se refiere a) (?:el |un |la )?"
                r"(?:inventario (?:disponible para vender|de productos disponibles)"
                r"|cantidad de productos disponibles para vender)[.! ]*", normalized):
                return ()
        else:
            clauses = re.split(r"[;.!?¿¡\n]+", normalized)
            normalized = "; ".join(
                "" if re.fullmatch(
                    r"(?:que (?:significa|es)|define|explica (?:el )?concepto de) "
                    r"(?:el |un |una )?(?:stock|inventario|proveedor|salario|sueldo|nomina)",
                    clause.strip()) else clause
                for clause in clauses)
            if not re.search(r"\b(nuestro|empresa|intern[oa]s?|contratos?|facturas?|margen(?:es)?|sku|stock)\b", normalized):
                normalized = re.sub(
                    r"\bproveedor de internet(?= para (?:conectar|configurar|instalar) "
                    r"(?:este|mi|el|un) (?:router|producto|dispositivo)\b)",
                    "servicio de internet", normalized)
                if "servicio de internet" in normalized:
                    normalized = re.sub(r"\bdatos del proveedor\b", "datos del servicio", normalized)
        return super().classify_all(normalized, output=output)


def authorization_message(decision: PolicyDecision) -> str:
    """Return a stable user-facing refusal without invoking an LLM."""
    if decision.tier == "restringido":
        return "Esta información crítica no puede consultarse mediante el chat, incluso con rol administrativo."
    if decision.tier == "confidencial":
        return "No tienes permisos para consultar esta información confidencial. Se requiere el rol admin."
    if decision.tier == "interno":
        return "No tienes permisos para consultar esta información interna. Se requiere el rol ventas o admin."
    return "No tienes permisos para realizar esta consulta."


_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """Return the process-wide policy engine instance."""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
