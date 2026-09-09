import { cookies } from "next/headers";
import { getDoc, visibleDocs } from "../../../lib/docs.js";

function session() {
  try {
    return JSON.parse(cookies().get("demo_user")?.value || "null");
  } catch {
    return null;
  }
}

export async function GET(req) {
  const user = session();
  if (!user) return Response.json({ error: "No autenticado" }, { status: 401 });
  const id = new URL(req.url).searchParams.get("id");
  if (!id) return Response.json({ docs: visibleDocs(user.roles || []) });
  const res = getDoc(id, user.roles || []);
  if (res.status === 404) return Response.json({ error: "Documento inexistente" }, { status: 404 });
  if (res.status === 403)
    return Response.json({ error: `Permiso denegado para rol [${(user.roles || []).join(", ")}]`, id, tier: res.tier }, { status: 403 });
  return Response.json({ id: res.doc.id, title: res.doc.title, body: res.doc.body, tier: res.doc.tier });
}
