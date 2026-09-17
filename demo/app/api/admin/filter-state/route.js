import { cookies } from "next/headers";
import { isAdmin } from "../../../../lib/shop.js";
import { readSessionToken } from "../../../../lib/session.js";

const CHAT_API_URL = (process.env.NEXT_PUBLIC_CHAT_API_URL || "http://localhost:8001").replace(/\/$/, "");

function session() {
  return readSessionToken(cookies().get("demo_user")?.value);
}

export async function GET() {
  const user = session();
  if (!user || !isAdmin(user)) {
    return Response.json(
      { error: "No autorizado: solo admin puede leer el estado del filtro" },
      { status: 403 }
    );
  }
  const response = await fetch(`${CHAT_API_URL}/api/v1/security/state`, {
    headers: process.env.CHAT_SERVICE_TOKEN
      ? { "X-Chat-Service-Token": process.env.CHAT_SERVICE_TOKEN }
      : {},
    cache: "no-store",
  });
  if (!response.ok) {
    return Response.json({ error: "Chat Service no disponible" }, { status: 502 });
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
