import { cookies } from "next/headers";
import { getFilterState } from "../../../../lib/filter-state.js";
import { isAdmin } from "../../../../lib/shop.js";

function session() {
  try {
    return JSON.parse(cookies().get("demo_user")?.value || "null");
  } catch {
    return null;
  }
}

export async function GET() {
  const user = session();
  if (!user || !isAdmin(user)) {
    return Response.json(
      { error: "No autorizado: solo admin puede leer el estado del filtro" },
      { status: 403 }
    );
  }
  return Response.json(getFilterState());
}
