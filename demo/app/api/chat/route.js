import { cookies } from "next/headers";
import { resolveSessionUser } from "../../../lib/shop.js";

const CHAT_API_URL = (process.env.NEXT_PUBLIC_CHAT_API_URL || "http://localhost:8000").replace(/\/$/, "");

function session() {
  try {
    return JSON.parse(cookies().get("demo_user")?.value || "null");
  } catch {
    return null;
  }
}

export async function POST(req) {
  const rawUser = session();
  const user = resolveSessionUser(rawUser);
  const { text } = await req.json().catch(() => ({}));
  
  if (!text || !text.trim()) {
    return Response.json({ error: "Texto vacío" }, { status: 400 });
  }

  try {
    // Reenviar la petición al Backend Demo (Chat Service)
    const response = await fetch(`${CHAT_API_URL}/api/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text,
        user: {
          id: user.id,
          name: user.name,
          email: user.email,
          roles: user.roles,
          avatar: user.avatar,
          puesto: user.puesto,
          authenticated: user.authenticated,
        },
        context: {
          channel: "demo-chat",
        },
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: "Error desconocido" }));
      return Response.json(
        { error: errorData.error || "Error del backend de chat" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return Response.json(data);

  } catch (error) {
    console.error("Error al comunicar con Chat Service:", error);
    return Response.json(
      { 
        error: "Error de comunicación con el servicio de chat",
        friendly: true 
      },
      { status: 502 }
    );
  }
}
