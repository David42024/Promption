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


@dataclass(frozen=True)
class ResourcePolicy:
    policy_id: str
    resource: str
    tier: str
    tool_name: Optional[str]
    patterns: tuple[str, ...]
    confidence: float = 0.95


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    matched: bool
    policy_id: str
    resource: str
    tier: str
    tool_name: Optional[str]
    required_roles: tuple[str, ...]
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "matched": self.matched,
            "policy_id": self.policy_id,
            "resource": self.resource,
            "tier": self.tier,
            "tool_name": self.tool_name,
            "required_roles": list(self.required_roles),
            "confidence": self.confidence,
            "reason": self.reason,
        }


RESOURCE_POLICIES = (
    ResourcePolicy(
        policy_id="confidential.credentials",
        resource="internal_credentials",
        tier="restringido",
        tool_name=None,
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
        tool_name="getEmployees",
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
        tool_name="getVIPClients",
        patterns=(
            r"\b(cliente(?:s)?\s+vip|vip\s*\d*|empresa\s+alpha|grupo\s+beta|gamma\s+innovaciones)\b",
            r"\b(descuento\s+preferente|responsable\s+de\s+cuenta)\b",
        ),
        confidence=0.97,
    ),
    ResourcePolicy(
        policy_id="confidential.financial_kpis",
        resource="financial_kpis",
        tier="confidencial",
        tool_name="getKPIStats",
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
        tool_name="getRevenueReport",
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
        tool_name="getTopProducts",
        patterns=(
            r"\b(top\s*\d*\s+productos|productos?\s+mas\s+vendidos|margen\s+real\s+por\s+producto|unidades\s+vendidas\s+por\s+sku)\b",
        ),
        confidence=0.96,
    ),
    ResourcePolicy(
        policy_id="confidential.admin_profile",
        resource="employee_admin_profile",
        tier="confidencial",
        tool_name="getEmployees",
        patterns=(
            r"\b(informacion|datos|perfil|detalle(?:s)?)\b.{0,40}\b(del\s+admin|administrador|director\s+general|jefe)\b",
        ),
        confidence=0.93,
    ),
    ResourcePolicy(
        policy_id="internal.marketing_campaigns",
        resource="marketing_campaigns",
        tier="interno",
        tool_name="getMarketingCampaigns",
        patterns=(
            r"\b(campa\w*|marketing|voltagear|back\s+to\s+school|black\s+friday\s+warmup|roi|roas|ctr\s+ads)\b",
        ),
        confidence=0.97,
    ),
    ResourcePolicy(
        policy_id="internal.stock",
        resource="internal_stock",
        tier="interno",
        tool_name="getStockInfo",
        patterns=(
            r"\b(stock\s+critico|unidades\s+(?:restantes|disponibles)|almacen|reponiendo|rotura\s+de\s+stock|proveedor(?:es)?|margen\s+con)\b",
        ),
        confidence=0.94,
    ),
    ResourcePolicy(
        policy_id="internal.promotions",
        resource="internal_promotions",
        tier="interno",
        tool_name="getPromotions",
        patterns=(
            r"\b(descuento|codigo)\b.{0,45}\b(emplead\w*|interno|sin\s+aprobacion|con\s+aprobacion|jefe|excepcional)\b",
            r"\b(empleado-?25|desc-?50-?interno|politica(?:s)?\s+comercial(?:es)?)\b",
        ),
        confidence=0.96,
    ),
    ResourcePolicy(
        policy_id="public.shipping",
        resource="shipping_and_returns",
        tier="publico",
        tool_name="getShippingPolicy",
        patterns=(
            r"\b(envio(?:s)?|devolucion(?:es)?|garantia(?:s)?|canarias|baleares|entrega|cuanto\s+tarda)\b",
        ),
        confidence=0.92,
    ),
    ResourcePolicy(
        policy_id="public.catalog",
        resource="product_catalog",
        tier="publico",
        tool_name="getCatalogSummary",
        patterns=(
            r"\b(catalogo|producto(?:s)?|portatil(?:es)?|smartphone(?:s)?|auricular(?:es)?|tablet(?:s)?|reloj(?:es)?|gaming)\b",
        ),
        confidence=0.88,
    ),
    ResourcePolicy(
        policy_id="public.brand",
        resource="brand_information",
        tier="publico",
        tool_name="getBrandInfo",
        patterns=(
            r"\b(horario(?:s)?|contacto|direccion\s+de\s+la\s+tienda|telefono\s+de\s+la\s+tienda|promption\s+shop|quienes\s+son)\b",
        ),
        confidence=0.88,
    ),
)


def normalize_text(text: str) -> str:
    """Normalize accents, case and whitespace without changing semantic content."""
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value.lower()).strip()


class PolicyEngine:
    """Classify a requested business resource and enforce its tier ACL."""

    def __init__(self, policies: Iterable[ResourcePolicy] = RESOURCE_POLICIES):
        self.policies = tuple(policies)
        self._compiled = tuple(
            (policy, tuple(re.compile(pattern, re.IGNORECASE) for pattern in policy.patterns))
            for policy in self.policies
        )

    def classify(self, text: str) -> Optional[ResourcePolicy]:
        normalized = normalize_text(text)
        for policy, patterns in self._compiled:
            if any(pattern.search(normalized) for pattern in patterns):
                return policy
        return None

    def evaluate(self, text: str, roles: Iterable[str]) -> PolicyDecision:
        role_set = {str(role).strip().lower() for role in roles if str(role).strip()}
        policy = self.classify(text)
        if policy is None:
            return PolicyDecision(
                allowed=True,
                matched=False,
                policy_id="public.general",
                resource="general_assistance",
                tier="publico",
                tool_name=None,
                required_roles=(),
                confidence=0.5,
                reason="No protected business resource was identified",
            )

        allowed_roles = TIER_ALLOWED_ROLES[policy.tier]
        allowed = bool(role_set & allowed_roles)
        required_roles = tuple(sorted(allowed_roles)) if policy.tier != "publico" else ()
        reason = (
            f"Role authorized for tier {policy.tier}"
            if allowed
            else f"Insufficient scope for tier {policy.tier}"
        )
        return PolicyDecision(
            allowed=allowed,
            matched=True,
            policy_id=policy.policy_id,
            resource=policy.resource,
            tier=policy.tier,
            tool_name=policy.tool_name,
            required_roles=required_roles,
            confidence=policy.confidence,
            reason=reason,
        )


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
