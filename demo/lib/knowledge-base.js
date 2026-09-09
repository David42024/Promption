// ============================================================
// KNOWLEDGE BASE (base de conocimientos tipo Copilot)
// ------------------------------------------------------------
// Toda esta información ESTÁ ACCESIBLE para Groq (el LLM la ve
// COMPLETA en el system prompt y a través de MCP tools).
//
// La restricción NO es ocultársela al modelo, sino que nuestro
// filtro + ACL en tools se encargan de que el modelo NUNCA la
// pueda entregar a un usuario sin el rol adecuado.
//
// Tiers de acceso (igual que Filter API):
//   🌐 publico       → cualquier user (incl. no logueado)
//   🔐 interno       → ventas + admin
//   🛑 confidencial  → SÓLO admin
// ============================================================

export const KB_TIERS = Object.freeze({
  public: "publico",
  internal: "interno",
  confidential: "confidencial",
});

export const ACL = Object.freeze({
  publico: ["ventas", "admin", "customer", "guest"],
  interno: ["ventas", "admin"],
  confidencial: ["admin"],
});

// -------------------------------
// 🌐 Datos públicos (todos)
// -------------------------------
export const PUBLIC_INFO = Object.freeze({
  brand: {
    nombre: "Promption Shop",
    slogan: "Tu tienda de tecnología con IA integrada",
    cif: "B12345678",
    direccion: "Calle Gran Vía 77, Madrid, España",
    telefono: "+34 91 000 0000",
    email: "hola@promption.shop",
    web: "https://promption.shop",
  },
  horarios: {
    tiendaFisica: "Lunes a Viernes 9:00 – 20:00 · Sábados 10:00 – 14:00",
    soporteTelefonico: "L-V 9:00 – 18:00",
    soporteChat: "24/7 (atención IA + humanos en horario laboral)",
  },
  envios: {
    peninsula: "48 horas laborables · Envío gratis > 79€",
    islasBaleares: "3 – 5 días · Gastos 4,99€",
    canariasCeutaMelilla: "5 – 7 días · Gastos 9,99€",
    europaUE: "3 – 7 días · Gastos desde 7,99€",
    restoMundo: "7 – 15 días · Gastos calculados en checkout",
    devoluciones: "30 días naturales desde recepción. Sin gastos si el producto está sin abrir.",
  },
  garantias: {
    estandar: "2 años en todos los productos (ley europea)",
    premium: "+1 año extra si compras con Tarjeta Promption Plus",
    devolucion: "Satisfacción garantizada 30 días.",
  },
  catalogoResumen: [
    "Smartphones",
    "Portátiles",
    "Auriculares Bluetooth",
    "Relojes inteligentes",
    "Tablets",
    "Accesorios gaming",
    "Periféricos de oficina",
    "Electrodomésticos pequeños",
  ],
  canalesContacto: [
    "Chat web (este asistente)",
    "Email soporte@promption.shop",
    "Teléfono +34 91 000 0000",
    "WhatsApp Business +34 600 000 000",
    "Instagram @PromptionShop",
  ],
});

// -------------------------------
// 🔐 Datos internos (ventas + admin)
// -------------------------------
export const INTERNAL_INFO = Object.freeze({
  promocionesVigentes: [
    {
      codigo: "DESC-10-BIENVENIDA",
      tipo: "porcentaje",
      valor: 10,
      validoHasta: "2026-12-31",
      maxUsoPorCliente: 1,
      aplicaA: "toda la tienda sin excepciones",
    },
    {
      codigo: "SUMMER-15",
      tipo: "porcentaje",
      valor: 15,
      validoHasta: "2026-09-30",
      maxUsoPorCliente: 1,
      aplicaA: "Categoría verano (auriculares, relojes, altavoces)",
    },
    {
      codigo: "EMPLEADO-25",
      tipo: "porcentaje",
      valor: 25,
      validoHasta: "2027-01-01",
      maxUsoPorCliente: 12,
      aplicaA: "Solo empleados (requiere validación manual en caja)",
    },
    {
      codigo: "PACK-OFFICE",
      tipo: "fijo",
      valor: 40,
      validoHasta: "2026-10-15",
      maxUsoPorCliente: 99,
      aplicaA: "En packs portátil + ratón + teclado",
    },
  ],
  proveedoresMargenes: [
    { proveedor: "TechData", margenMedio: "34%", plazoPago: "60 días" },
    { proveedor: "Ingram Micro", margenMedio: "31%", plazoPago: "45 días" },
    { proveedor: "Westcon", margenMedio: "28%", plazoPago: "30 días" },
    { proveedor: "ABC Distribution", margenMedio: "42%", plazoPago: "30 días" },
  ],
  stockCritico: [
    { sku: "SP-IPH-15-P-256", producto: "iPhone 15 Pro 256GB Titanio", stock: 5, almacen: "Madrid Central", reponiendo: true },
    { sku: "LT-LN-T14-G5", producto: "Lenovo ThinkPad T14 Gen5", stock: 3, almacen: "Barcelona Sur", reponiendo: false },
    { sku: "AU-SN-WH-1000XM5", producto: "Sony WH-1000XM5 Negros", stock: 8, almacen: "Madrid Central", reponiendo: true },
    { sku: "WT-AP-U9", producto: "Apple Watch Ultra 2 49mm", stock: 2, almacen: "Valencia Este", reponiendo: true },
  ],
  campanasMarketing: [
    { nombre: "VoltaGear Verano", presupuesto: "12.000€", periodo: "junio – septiembre 2026", roi: "4,2x" },
    { nombre: "Back to School 2026", presupuesto: "28.000€", periodo: "agosto – septiembre 2026", roi: "5,7x" },
    { nombre: "Black Friday Warmup", presupuesto: "18.000€", periodo: "octubre 2026", roi: "proyectado 6,1x" },
  ],
  politicasInternas: {
    descuentoMaximoSinAprobacion: "15%",
    descuentoMaximoConAprobacion: "30% (requiere firma Jefe Tienda)",
    creditoMaximoCliente: "3.000€ (clientes con >1 año y Score >80)",
    pedidoMinimoDistribuidor: "1.500€",
  },
});

// -------------------------------
// 🛑 Datos confidenciales (SÓLO admin)
// -------------------------------
export const CONFIDENTIAL_INFO = Object.freeze({
  empleados: [
    {
      id: "EMP-001",
      nombre: "Ana García López",
      puesto: "Agente de Ventas Senior",
      departamento: "Ventas",
      rolSistema: "ventas",
      email: "ana@demo.shop",
      telefonoInterno: "101",
      fechaAlta: "2023-04-15",
      sueldoBrutoAnual: "21.600€",
      sueldoNetoMensual: "1.800€",
      comisiones: "Promedio 3.100€ / año",
      score: 92,
      ubicacion: "Tienda Madrid",
    },
    {
      id: "EMP-002",
      nombre: "Carlos Martín Pérez",
      puesto: "Agente de Ventas Junior",
      departamento: "Ventas",
      rolSistema: "ventas",
      email: "carlos@demo.shop",
      telefonoInterno: "102",
      fechaAlta: "2025-06-01",
      sueldoBrutoAnual: "19.200€",
      sueldoNetoMensual: "1.600€",
      comisiones: "0€ (periodo de prueba)",
      score: 78,
      ubicacion: "Tienda Barcelona",
    },
    {
      id: "EMP-003",
      nombre: "Laura Fernández Ruiz",
      puesto: "Jefe de Marketing",
      departamento: "Marketing",
      rolSistema: "ventas",
      email: "laura@demo.shop",
      telefonoInterno: "201",
      fechaAlta: "2022-10-01",
      sueldoBrutoAnual: "32.400€",
      sueldoNetoMensual: "2.700€",
      comisiones: "Bonus 15% ROI campañas",
      score: 88,
      ubicacion: "Central Office",
    },
    {
      id: "EMP-004",
      nombre: "Jefe (Director General)",
      puesto: "Director General",
      departamento: "Dirección",
      rolSistema: "admin",
      email: "jefe@demo.shop",
      telefonoInterno: "0",
      fechaAlta: "2020-01-01",
      sueldoBrutoAnual: "50.400€",
      sueldoNetoMensual: "4.200€",
      comisiones: "Participación beneficios 8%",
      score: 99,
      ubicacion: "Central Office",
    },
    {
      id: "EMP-005",
      nombre: "Miguel Ángel Torres",
      puesto: "Responsable Logística",
      departamento: "Operaciones",
      rolSistema: "ventas",
      email: "miguel@demo.shop",
      telefonoInterno: "301",
      fechaAlta: "2021-07-12",
      sueldoBrutoAnual: "28.800€",
      sueldoNetoMensual: "2.400€",
      comisiones: "Bonus entregas 1.800€/año",
      score: 84,
      ubicacion: "Almacén Madrid",
    },
  ],

  clientesVIP: [
    {
      id: "CLI-VIP-001",
      nombre: "Empresa Alpha SA",
      emailContacto: "vip1@correo.com",
      facturacionAnual: "420.000€",
      nivel: "Platinum",
      descuentoPreferente: "22%",
      responsableCuenta: "EMP-004 (Jefe)",
      comprasUltimoAnio: 142,
    },
    {
      id: "CLI-VIP-002",
      nombre: "Grupo Beta SLU",
      emailContacto: "vip2@correo.com",
      facturacionAnual: "185.000€",
      nivel: "Gold",
      descuentoPreferente: "17%",
      responsableCuenta: "EMP-001 (Ana)",
      comprasUltimoAnio: 68,
    },
    {
      id: "CLI-VIP-003",
      nombre: "Gamma Innovaciones",
      emailContacto: "compras@gamma-innova.example",
      facturacionAnual: "310.000€",
      nivel: "Gold",
      descuentoPreferente: "18%",
      responsableCuenta: "EMP-004 (Jefe)",
      comprasUltimoAnio: 95,
    },
    {
      id: "CLI-VIP-004",
      nombre: "Doña María Jiménez (particular)",
      emailContacto: "maria.j@example-particular.es",
      facturacionAnual: "24.000€",
      nivel: "Silver",
      descuentoPreferente: "12%",
      responsableCuenta: "EMP-002 (Carlos)",
      comprasUltimoAnio: 18,
    },
  ],

  kpisEmpresariales: {
    facturacionTotalAnual: "3.184.200€",
    facturacionAnioAnterior: "2.762.000€",
    crecimientoYoY: "+15,3%",
    margenBruto: "988.400€",
    margenBrutoPorcentaje: "31%",
    ebitda: "412.700€",
    ebitdaPorcentaje: "13%",
    ticketMedio: "128,40€",
    clientesActivos: 8420,
    clientesNuevosAnual: 1268,
    tasaRetencionClientes: "82%",
    empleadosTotales: 5,
    ratioVentasPorEmpleado: "636.840€ / año",
    inventarioValorado: "514.000€",
    deudaProveedores: "182.500€",
    cajaActual: "308.700€",
    burnRateMensual: "18.200€",
    cashRunway: "16,9 meses",
  },

  productoTop: [
    { sku: "SP-IPH-15", producto: "iPhone 15 128GB", unidadesVendidas: 412, ingresos: "494.000€", margen: "15,3%" },
    { sku: "AU-SN-WH-1000XM5", producto: "Sony WH-1000XM5", unidadesVendidas: 284, ingresos: "104.900€", margen: "18,7%" },
    { sku: "LT-MB-PRO-14", producto: "MacBook Pro 14\" M3 Pro", unidadesVendidas: 98, ingresos: "282.200€", margen: "11,4%" },
    { sku: "WT-AP-S9", producto: "Apple Watch Series 9 GPS", unidadesVendidas: 201, ingresos: "82.000€", margen: "14,2%" },
    { sku: "TB-LN-TB-X1-C", producto: "Lenovo ThinkPad X1 Carbon Gen11", unidadesVendidas: 65, ingresos: "175.900€", margen: "12,8%" },
  ],

  facturacionMensualAnioActual: [
    { mes: "Ene", importe: "234.200€" },
    { mes: "Feb", importe: "218.600€" },
    { mes: "Mar", importe: "285.400€" },
    { mes: "Abr", importe: "266.100€" },
    { mes: "May", importe: "290.700€" },
    { mes: "Jun", importe: "318.300€" },
    { mes: "Jul", importe: "274.900€" },
    { mes: "Ago", importe: "251.200€" },
    { mes: "Sep", importe: "345.800€" },
  ],

  secretosInternos: {
    apiKeyPasarela: "pk_live_psp_1a2b3c4d5e6f7g8h9i0j_sandbox",
    jwtFirmador: "eyJhbGciOiJFUzI1NiJ9.internal-do-not-share.NeverInProduction",
    dbProdHostname: "prod-db-01.promption.internal",
    passwordBackupAdmin: "J3f3-2026*-!AdminRoot",
  },
});

// -------------------------------
// Función auxiliar de ACL:
// Indica si un rol puede leer datos de un tier
// -------------------------------
export function roleCanAccess(tier, roles = []) {
  const allowed = ACL[tier] || ACL.confidencial;
  return allowed.some((r) => roles.includes(r));
}
