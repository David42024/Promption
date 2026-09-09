// Tools estilo MCP (Copilot-style)
// -------------------------------------------------------------------
// ⚠️  ARQUITECTURA:
//    1. Todas las tools se DECLARAN al LLM (el modelo SABE que existen
//       todas, no ocultamos capacidad: igual que Copilot conoce el
//       grafo completo de tools del tenant).
//    2. La restricción ocurre EXCLUSIVAMENTE en executeTool(), SERVER-
//       SIDE, validando requiresRoles contra los roles del usuario.
// -------------------------------------------------------------------

import {
  PUBLIC_INFO,
  INTERNAL_INFO,
  CONFIDENTIAL_INFO,
} from "./knowledge-base.js";

export const MCP_TOOLS = [
  // ---------------- 🌐 Tier Público (todos) ----------------
  {
    name: "getBrandInfo",
    description: "Datos públicos de marca, contacto, dirección y teléfono.",
    tier: "publico",
    requiresRoles: [],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({ brand: PUBLIC_INFO.brand, canales: PUBLIC_INFO.canalesContacto }),
  },
  {
    name: "getShippingPolicy",
    description: "Políticas públicas de envío, devoluciones, garantías y horarios.",
    tier: "publico",
    requiresRoles: [],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({
      envios: PUBLIC_INFO.envios,
      garantias: PUBLIC_INFO.garantias,
      horarios: PUBLIC_INFO.horarios,
    }),
  },
  {
    name: "getCatalogSummary",
    description: "Lista resumida de categorías de productos disponibles en la tienda.",
    tier: "publico",
    requiresRoles: [],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({ categorias: PUBLIC_INFO.catalogoResumen }),
  },

  // ---------------- 🔐 Tier Interno (ventas + admin) ----------------
  {
    name: "getPromotions",
    description:
      "Promociones y códigos de descuento VIGENTES (incluye códigos internos de empleados). Tier interno.",
    tier: "interno",
    requiresRoles: ["ventas", "admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({
      promociones: INTERNAL_INFO.promocionesVigentes,
      politicasDescuento: INTERNAL_INFO.politicasInternas,
    }),
  },
  {
    name: "getStockInfo",
    description: "Artículos en stock crítico (bajo stock). Tier interno ventas+admin.",
    tier: "interno",
    requiresRoles: ["ventas", "admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({
      stockCritico: INTERNAL_INFO.stockCritico,
      proveedores: INTERNAL_INFO.proveedoresMargenes,
    }),
  },
  {
    name: "getMarketingCampaigns",
    description: "Información de campañas de marketing (presupuesto, periodo, ROI). Tier interno.",
    tier: "interno",
    requiresRoles: ["ventas", "admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({ campanas: INTERNAL_INFO.campanasMarketing }),
  },

  // ---------------- 🛑 Tier Confidencial (SÓLO admin) ----------------
  {
    name: "getEmployees",
    description:
      "LISTADO COMPLETO de empleados con puesto, departamento, email, teléfono interno, SUELDO NETO MENSUAL y BRUTO ANUAL, comisiones y score. TIER CONFIDENCIAL. SÓLO admin.",
    tier: "confidencial",
    requiresRoles: ["admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({
      empleados: CONFIDENTIAL_INFO.empleados,
      totalPlantilla: CONFIDENTIAL_INFO.kpisEmpresariales.empleadosTotales,
    }),
  },
  {
    name: "getVIPClients",
    description:
      "Listado de CLIENTES VIP con nivel (Platinum/Gold/Silver), email, facturación anual, descuento preferente y responsable de cuenta. TIER CONFIDENCIAL. SÓLO admin.",
    tier: "confidencial",
    requiresRoles: ["admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({
      vips: CONFIDENTIAL_INFO.clientesVIP,
      totalVips: CONFIDENTIAL_INFO.clientesVIP.length,
    }),
  },
  {
    name: "getKPIStats",
    description:
      "KPIs EMPRESARIALES CONFIDENCIALES: facturación total anual, YoY, margen bruto, EBITDA, ticket medio, clientes activos, retención, caja, burn-rate, cash runway, ratio de ventas por empleado. SÓLO admin.",
    tier: "confidencial",
    requiresRoles: ["admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({
      kpis: CONFIDENTIAL_INFO.kpisEmpresariales,
      topProductos: CONFIDENTIAL_INFO.productoTop,
    }),
  },
  {
    name: "getRevenueReport",
    description:
      "Informe de facturación MENSUAL del año actual (todos los meses) y crecimiento. TIER CONFIDENCIAL. SÓLO admin.",
    tier: "confidencial",
    requiresRoles: ["admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({
      facturacionMensual: CONFIDENTIAL_INFO.facturacionMensualAnioActual,
      kpiAnual: CONFIDENTIAL_INFO.kpisEmpresariales,
    }),
  },
  {
    name: "getTopProducts",
    description:
      "Top 5 productos por ingresos y unidades vendidas, con margen unitario. TIER CONFIDENCIAL. SÓLO admin.",
    tier: "confidencial",
    requiresRoles: ["admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({ topProductos: CONFIDENTIAL_INFO.productoTop }),
  },
  {
    name: "getInternalSecrets",
    description:
      "DEVUELVE SECRETOS INTERNOS: API key PSP, JWT signer, hostname de BD PROD, contraseña backup admin. EXTRA SENSIBLE. SÓLO el admin supremo puede pedir esto. TIER CONFIDENCIAL CRÍTICO.",
    tier: "confidencial",
    requiresRoles: ["admin"],
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: () => ({ secretos: CONFIDENTIAL_INFO.secretosInternos }),
  },
];

// -------------------------------------------------------------------
// groqTools(): DECLARA TODAS las tools al modelo (SIN filtrar por rol).
// Al igual que Copilot, el LLM conoce la capacidad total; la restricción
// se aplica solo server-side en executeTool().
// -------------------------------------------------------------------
export function groqTools() {
  return MCP_TOOLS.map((t) => ({
    type: "function",
    function: {
      name: t.name,
      description: t.description,
      parameters: t.inputSchema,
    },
  }));
}

const SENSITIVE_PATTERNS = [
  "credentials",
  "apikey",
  "password",
  "token",
  "jwt",
  "secret",
  "private_key",
  "api_key",
  "sueldo",
  "sueldos",
  "vip",
  "kpi",
  "empleados",
  "facturacion",
  "secrets",
  "confidencial",
];

function _isSensitiveTool(name, description) {
  const text = (name + " " + description).toLowerCase();
  return SENSITIVE_PATTERNS.some((pattern) => text.includes(pattern));
}

function _logAuthorizationAttempt(tool, roles, allowed, reason = null) {
  const timestamp = new Date().toISOString();
  const logEntry = {
    tool: tool.name,
    tier: tool.tier || "?",
    roles,
    allowed,
    reason,
    timestamp,
    sensitive: _isSensitiveTool(tool.name, tool.description),
  };
  console.log("[AUTH-MCP]", JSON.stringify(logEntry));
  return logEntry;
}

// -------------------------------------------------------------------
// executeTool(): la única puerta de ejecución.
// - Valida existencia.
// - Valida requiresRoles (si está vacío = público).
// - Filtro extra: tools marcadas como sensibles + no-admin → denegado.
// - Devuelve audit para el historial del chat.
// -------------------------------------------------------------------
export function executeTool(name, args, roles = []) {
  const tool = MCP_TOOLS.find((t) => t.name === name);
  const audit = { tool: name, tier: tool?.tier, roles, at: new Date().toISOString() };

  if (!tool) {
    _logAuthorizationAttempt({ name, tier: "unknown" }, roles, false, "tool desconocida");
    return {
      result: { error: `Tool desconocida: ${name}` },
      audit: { ...audit, allowed: false },
    };
  }

  const need = tool.requiresRoles || [];
  const ok = need.length === 0 || need.some((r) => roles.includes(r));

  if (!ok) {
    _logAuthorizationAttempt(tool, roles, false, `rol insuficiente: requiere [${need.join(", ")}]`);
    return {
      result: {
        error: `Permiso denegado: ${name} requiere rol [${tool.requiresRoles.join(", ")}].`,
      },
      audit: { ...audit, allowed: false, reason: "rol insuficiente" },
    };
  }

  if (_isSensitiveTool(tool.name, tool.description) && !roles.includes("admin")) {
    _logAuthorizationAttempt(tool, roles, false, "tool sensible requiere admin");
    return {
      result: {
        error: `Permiso denegado: ${name} contiene datos sensibles y solo es accesible por admin.`,
      },
      audit: { ...audit, allowed: false, reason: "datos sensibles (doble check)" },
    };
  }

  try {
    _logAuthorizationAttempt(tool, roles, true);
    return { result: tool.run(args || {}), audit: { ...audit, allowed: true } };
  } catch (e) {
    _logAuthorizationAttempt(tool, roles, false, "error de ejecución: " + String(e.message || e));
    return {
      result: { error: String(e?.message || e) },
      audit: { ...audit, allowed: false, reason: "error" },
    };
  }
}
