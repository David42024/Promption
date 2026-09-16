export const DEMO_USERS = [
  {
    email: "ana@demo.shop",
    password: "demo123",
    id: "EMP-001",
    name: "Ana García",
    roles: ["ventas"],
    avatar: "👩‍💼",
    puesto: "Agente Senior Ventas",
  },
  {
    email: "carlos@demo.shop",
    password: "demo123",
    id: "EMP-002",
    name: "Carlos Martín",
    roles: ["ventas"],
    avatar: "🧑‍💼",
    puesto: "Agente Junior Ventas",
  },
  {
    email: "laura@demo.shop",
    password: "demo123",
    id: "EMP-003",
    name: "Laura Fernández",
    roles: ["ventas"],
    avatar: "👩‍💻",
    puesto: "Jefa de Marketing",
  },
  {
    email: "jefe@demo.shop",
    password: "demo123",
    id: "EMP-004",
    name: "Director General",
    roles: ["admin", "ventas"],
    avatar: "👑",
    puesto: "Director General",
  },
  {
    email: "miguel@demo.shop",
    password: "demo123",
    id: "EMP-005",
    name: "Miguel Torres",
    roles: ["ventas"],
    avatar: "🧑‍🏭",
    puesto: "Responsable Logística",
  },
  {
    email: "cliente@demo.shop",
    password: "demo123",
    id: "CLI-CUST-01",
    name: "Cliente VIP María",
    roles: ["customer"],
    avatar: "🛍️",
    puesto: "Cliente particular",
  },
];

export function findUser(email, password) {
  const normalizedEmail = String(email || "").trim().toLowerCase();
  const normalizedPassword = String(password || "").trim();
  return DEMO_USERS.find(
    user => user.email === normalizedEmail && user.password === normalizedPassword
  ) || null;
}

export function publicUser(user) {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    roles: user.roles,
    avatar: user.avatar,
    puesto: user.puesto,
  };
}

export function isAdmin(user) {
  return Boolean(user?.roles?.includes("admin"));
}

export const GUEST_USER = Object.freeze({
  id: "GUEST-000",
  name: "Visitante",
  email: "guest@promption.shop",
  roles: ["guest"],
  avatar: "👤",
  puesto: "Usuario no autenticado",
  authenticated: false,
});

export function resolveSessionUser(session, options = {}) {
  const knownUser = session?.id
    ? DEMO_USERS.find(user => user.id === session.id && user.email === session.email)
    : null;
  if (knownUser) {
    return { ...publicUser(knownUser), authenticated: true };
  }
  return options.allowGuest === false ? null : { ...GUEST_USER };
}
