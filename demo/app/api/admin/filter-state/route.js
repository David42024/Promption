import { cookies } from "next/headers";
import { getFilterState } from "../../../../lib/filter-state.js";
import { isAdmin } from "../../../../lib/shop.js";
import { readSessionToken } from "../../../../lib/session.js";

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
  return Response.json(getFilterState());
}
