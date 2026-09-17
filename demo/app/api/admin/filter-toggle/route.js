import { cookies } from "next/headers";
import { isAdmin } from "../../../../lib/shop.js";
import { readSessionToken } from "../../../../lib/session.js";

const CHAT_API_URL = (process.env.NEXT_PUBLIC_CHAT_API_URL || "http://localhost:8001").replace(/\/$/, "");

function session() {
  return readSessionToken(cookies().get("demo_user")?.value);
}

export async function POST(req) {
  const user = session();
  if (!user || !isAdmin(user)) {
    return Response.json(
      { error: "No autorizado: solo admin puede cambiar el estado del filtro" },
      { status: 403 }
    );
  }
  const payload = await req.json().catch(() => ({}));
  const { action, enabled } = payload;
  const by = user.email || user.id || "admin";

  const normalizedAction = action === "output-guard" ? "output_guard" : (action || "filter");
  if (!["filter", "output_guard", "reset"].includes(normalizedAction)) {
    return Response.json({ error: "Acción desconocida: " + action }, { status: 400 });
  }
  const response = await fetch(`${CHAT_API_URL}/api/v1/security/state`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(process.env.CHAT_SERVICE_TOKEN
        ? { "X-Chat-Service-Token": process.env.CHAT_SERVICE_TOKEN }
        : {}),
    },
    body: JSON.stringify({
      action: normalizedAction,
      enabled: normalizedAction === "reset" ? null : Boolean(enabled),
      updated_by: by,
    }),
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    return Response.json({ error: detail || "Chat Service no disponible" }, { status: 502 });
  }
  const state = await response.json();
  return Response.json({
    filterEnabled: state.filter_enabled,
    outputGuardEnabled: state.output_guard_enabled,
    updatedAt: state.updated_at,
    updatedBy: state.updated_by,
    history: state.history || [],
  });
}
