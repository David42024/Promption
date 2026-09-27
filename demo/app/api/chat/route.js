import { randomUUID } from "node:crypto";
import { cookies } from "next/headers";
import { GUEST_USER } from "../../../lib/shop.js";
import { readSessionToken } from "../../../lib/session.js";
import { visibleDocs } from "../../../lib/docs.js";

export const maxDuration = 300;
const CHAT_API_URL = (process.env.CHAT_API_URL || process.env.NEXT_PUBLIC_CHAT_API_URL || "").replace(/\/$/, "");
const COOKIE_NAME = "chat_session";

function session() {
  return readSessionToken(cookies().get("demo_user")?.value) || { ...GUEST_USER };
}

function conversationId() {
  const cookieStore = cookies();
  const existing = cookieStore.get(COOKIE_NAME)?.value;
  if (existing && /^[0-9a-f-]{36}$/i.test(existing)) return existing;
  const id = randomUUID();
  cookieStore.set(COOKIE_NAME, id, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return id;
}

function userPayload(user) {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    roles: user.roles,
    avatar: user.avatar,
    puesto: user.puesto,
    authenticated: user.authenticated,
  };
}

function serviceHeaders() {
  return {
    "Content-Type": "application/json",
    ...(process.env.CHAT_SERVICE_TOKEN
      ? { "X-Chat-Service-Token": process.env.CHAT_SERVICE_TOKEN }
      : {}),
  };
}

export async function GET() {
  const user = session();
  const id = conversationId();
  try {
    const response = await fetch(`${CHAT_API_URL}/api/v1/conversation/history`, {
      method: "POST",
      headers: serviceHeaders(),
      cache: "no-store",
      body: JSON.stringify({ conversation_id: id, user: userPayload(user) }),
    });
    if (!response.ok) return Response.json({ error: "No se pudo cargar la conversación" }, { status: 502 });
    const data = await response.json();
    return Response.json({ messages: data.messages || [] });
  } catch {
    return Response.json({ error: "No se pudo cargar la conversación" }, { status: 502 });
  }
}

export async function DELETE() {
  cookies().set(COOKIE_NAME, randomUUID(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return Response.json({ ok: true });
}

export async function POST(req) {
  const user = session();
  const id = conversationId();
  const { text } = await req.json().catch(() => ({}));
  if (typeof text !== "string" || !text.trim()) {
    return Response.json({ error: "Texto vacío" }, { status: 400 });
  }

  try {
    const streaming = req.headers.get("accept")?.includes("text/event-stream");
    const response = await fetch(`${CHAT_API_URL}/api/v1/chat${streaming ? "/stream" : ""}`, {
      method: "POST",
      headers: serviceHeaders(),
      cache: "no-store",
      signal: req.signal,
      body: JSON.stringify({
        text,
        user: userPayload(user),
        context: {
          channel: "demo-chat",
          conversation_id: id,
          documents: user.authenticated
            ? visibleDocs(user.roles).map(({ id, title, tier }) => ({ id, title, tier }))
            : [],
        },
      }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return Response.json(
        { error: errorData.error || "Error del backend de chat" },
        { status: response.status }
      );
    }
    if (streaming) {
      return new Response(response.body, {
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache, no-transform",
          "X-Accel-Buffering": "no",
        },
      });
    }
    return Response.json(await response.json());
  } catch (error) {
    console.error("Error al comunicar con Chat Service:", error);
    return Response.json(
      { error: "Error de comunicación con el servicio de chat", friendly: true },
      { status: 502 }
    );
  }
}

export async function PATCH() {
  const user = session();
  const id = conversationId();
  try {
    const response = await fetch(`${CHAT_API_URL}/api/v1/chat/cancel`, {
      method: "POST",
      headers: serviceHeaders(),
      cache: "no-store",
      body: JSON.stringify({ conversation_id: id, user: userPayload(user) }),
    });
    if (!response.ok) return Response.json({ error: "No se pudo detener" }, { status: 502 });
    return Response.json(await response.json());
  } catch {
    return Response.json({ error: "No se pudo detener" }, { status: 502 });
  }
}
