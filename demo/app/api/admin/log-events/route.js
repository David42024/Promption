import { cookies } from "next/headers";
import { isAdmin } from "../../../../lib/shop.js";
import { readSessionToken } from "../../../../lib/session.js";

const FILTER_API_URL = (process.env.PIF_API_URL || process.env.NEXT_PUBLIC_PIF_API_URL || "https://promption.onrender.com").replace(/\/$/, "");
const ADMIN_API_KEY = process.env.PROMPTION_ADMIN_API_KEY || process.env.PIF_ADMIN_API_KEY || "";

function session() {
  return readSessionToken(cookies().get("demo_user")?.value);
}

export async function GET(req) {
  const user = session();
  if (!user || !isAdmin(user)) {
    return Response.json(
      { error: "No autorizado: solo admin puede leer logs" },
      { status: 403 }
    );
  }
  if (!ADMIN_API_KEY) {
    return Response.json(
      { error: "Falta PROMPTION_ADMIN_API_KEY en Vercel" },
      { status: 500 }
    );
  }

  const sourceUrl = new URL(req.url);
  const params = new URLSearchParams(sourceUrl.search);
  const upstream = `${FILTER_API_URL}/api/v1/logs/structured?${params}`;
  const r = await fetch(upstream, {
    headers: {
      "X-Promption-API-Key": ADMIN_API_KEY,
    },
    cache: "no-store",
  });
  const body = await r.text();
  return new Response(body, {
    status: r.status,
    headers: {
      "Content-Type": r.headers.get("Content-Type") || "application/json",
    },
  });
}
