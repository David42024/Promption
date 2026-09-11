// Sistema de configuración de permisos generalizable
// Este sistema permite definir permisos por rol para cualquier negocio

export const DEFAULT_PERMISSIONS = {
  // Tiers de información (configurables por negocio)
  tiers: {
    public: {
      key: "public",
      label: "Público",
      icon: "🌐",
      description: "Información accesible para cualquier usuario",
      allowedRoles: ["customer", "guest", "employee", "admin"],
      examples: ["Horarios", "Catálogo", "Garantías", "Contacto"]
    },
    internal: {
      key: "internal", 
      label: "Interno",
      icon: "🔐",
      description: "Información solo para empleados",
      allowedRoles: ["employee", "admin"],
      examples: ["Promociones internas", "Stock", "Proveedores", "Políticas comerciales"]
    },
    confidential: {
      key: "confidential",
      label: "Confidencial", 
      icon: "🛑",
      description: "Información sensible solo para administración",
      allowedRoles: ["admin"],
      examples: ["Sueldos", "KPIs financieros", "Secretos internos", "Datos VIP"]
    }
  },
  
  // Roles predefinidos (configurables)
  roles: {
    guest: {
      key: "guest",
      label: "Visitante",
      icon: "👤",
      description: "Usuario no autenticado",
      permissions: ["public"],
      tierAccess: ["public"]
    },
    customer: {
      key: "customer",
      label: "Cliente",
      icon: "🛍️", 
      description: "Cliente final del negocio",
      permissions: ["public"],
      tierAccess: ["public"]
    },
    ventas: {
      key: "ventas",
      label: "Ventas",
      icon: "💼",
      description: "Personal de ventas y marketing",
      permissions: ["public", "internal"],
      tierAccess: ["public", "internal"]
    },
    admin: {
      key: "admin",
      label: "Administrador",
      icon: "👑",
      description: "Personal con acceso completo",
      permissions: ["public", "internal", "confidential"],
      tierAccess: ["public", "internal", "confidential"]
    }
  },
  
  // Configuración de herramientas MCP por rol
  tools: {
    getPublicInfo: {
      name: "getPublicInfo",
      description: "Obtener información pública",
      allowedRoles: ["guest", "customer", "ventas", "admin"],
      tier: "public"
    },
    getInternalInfo: {
      name: "getInternalInfo", 
      description: "Obtener información interna",
      allowedRoles: ["ventas", "admin"],
      tier: "internal"
    },
    getConfidentialInfo: {
      name: "getConfidentialInfo",
      description: "Obtener información confidencial",
      allowedRoles: ["admin"],
      tier: "confidential"
    },
    manageUsers: {
      name: "manageUsers",
      description: "Gestionar usuarios del sistema",
      allowedRoles: ["admin"],
      tier: "confidential"
    },
    viewAnalytics: {
      name: "viewAnalytics",
      description: "Ver analytics y métricas",
      allowedRoles: ["ventas", "admin"],
      tier: "internal"
    }
  },
  
  // Configuración del filtro por tier
  filterSettings: {
    public: {
      strictness: "low",
      blockInjection: true,
      allowExtraction: false
    },
    internal: {
      strictness: "medium", 
      blockInjection: true,
      allowExtraction: false
    },
    confidential: {
      strictness: "high",
      blockInjection: true,
      allowExtraction: false
    }
  }
};

// Función para verificar si un rol tiene acceso a un tier
export function hasTierAccess(role, tier) {
  const roleConfig = DEFAULT_PERMISSIONS.roles[role];
  if (!roleConfig) return false;
  return roleConfig.tierAccess.includes(tier);
}

// Función para verificar si un rol puede usar una herramienta
export function canUseTool(role, toolName) {
  const toolConfig = DEFAULT_PERMISSIONS.tools[toolName];
  if (!toolConfig) return false;
  return toolConfig.allowedRoles.includes(role);
}

// Función para obtener tiers accesibles por un rol
export function getAccessibleTiers(role) {
  const roleConfig = DEFAULT_PERMISSIONS.roles[role];
  if (!roleConfig) return [];
  return roleConfig.tierAccess;
}

// Función para validar configuración personalizada
export function validateCustomConfig(config) {
  const errors = [];
  
  // Validar que todos los roles definidos tengan tierAccess
  if (config.roles) {
    Object.keys(config.roles).forEach(roleKey => {
      const role = config.roles[roleKey];
      if (!role.tierAccess || !Array.isArray(role.tierAccess)) {
        errors.push(`Rol ${roleKey} debe tener tierAccess array`);
      }
    });
  }
  
  // Validar que tiers tengan allowedRoles
  if (config.tiers) {
    Object.keys(config.tiers).forEach(tierKey => {
      const tier = config.tiers[tierKey];
      if (!tier.allowedRoles || !Array.isArray(tier.allowedRoles)) {
        errors.push(`Tier ${tierKey} debe tener allowedRoles array`);
      }
    });
  }
  
  return errors;
}

// Función para fusionar configuración personalizada con default
export function mergePermissionsConfig(customConfig) {
  const errors = validateCustomConfig(customConfig);
  if (errors.length > 0) {
    throw new Error(`Configuración inválida: ${errors.join(", ")}`);
  }
  
  return {
    tiers: { ...DEFAULT_PERMISSIONS.tiers, ...customConfig.tiers },
    roles: { ...DEFAULT_PERMISSIONS.roles, ...customConfig.roles },
    tools: { ...DEFAULT_PERMISSIONS.tools, ...customConfig.tools },
    filterSettings: { ...DEFAULT_PERMISSIONS.filterSettings, ...customConfig.filterSettings }
  };
}