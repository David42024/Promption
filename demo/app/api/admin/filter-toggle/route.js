import { cookies } from "next/headers";
import {
  setFilterEnabled,
  setOutputGuardEnabled,
  resetFilterState,
} from "../../../../lib/filter-state.js";
import { isAdmin } from "../../../../lib/shop.js";

function session() {
  try {
    return JSON.parse(cookies().get("demo_user")?.value || "null");
  } catch {
    return null;
  }
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

  if (action === "reset") {
    return Response.json(resetFilterState(by));
  }

  if (action === "output-guard") {
    return Response.json(
      setOutputGuardEnabled(Boolean(enabled), by)
    );
  }

  // Default: action "filter" (o vacío)
  if (action === "filter" || typeof enabled === "boolean" || !action) {
    return Response.json(
      setFilterEnabled(Boolean(enabled), by)
    );
  }

  return Response.json({ error: "Acción desconocida: " + action }, { status: 400 });
}
