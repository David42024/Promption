import { findUser, publicUser } from "../../../lib/shop.js";
import { cookies } from "next/headers";

export async function POST(req) {
  const { email, password } = await req.json().catch(() => ({}));
  const user = findUser(email || "", password || "");
  if (!user) {
    return Response.json({ error: "Credenciales demo inválidas" }, { status: 401 });
  }
  cookies().set("demo_user", JSON.stringify(publicUser(user)), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return Response.json({ user: publicUser(user) });
}

export async function DELETE() {
  cookies().delete("demo_user");
  return Response.json({ ok: true });
}
