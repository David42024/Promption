import { createHmac, timingSafeEqual } from "node:crypto";
import { resolveSessionUser } from "./shop.js";

const DEVELOPMENT_SECRET = "promption-demo-session-development-only";

function sessionSecret() {
  const configured = process.env.SESSION_SECRET || process.env.CHAT_SERVICE_TOKEN;
  if (configured) return configured;
  if (process.env.NODE_ENV === "production") {
    throw new Error("SESSION_SECRET is required in production");
  }
  return DEVELOPMENT_SECRET;
}

function signature(payload) {
  return createHmac("sha256", sessionSecret()).update(payload).digest("base64url");
}

export function createSessionToken(user) {
  const payload = Buffer.from(JSON.stringify(user), "utf8").toString("base64url");
  return `${payload}.${signature(payload)}`;
}

export function readSessionToken(value) {
  if (!value || typeof value !== "string") return null;
  const separator = value.lastIndexOf(".");
  if (separator <= 0) return null;
  const payload = value.slice(0, separator);
  const received = value.slice(separator + 1);
  const expected = signature(payload);
  const receivedBuffer = Buffer.from(received);
  const expectedBuffer = Buffer.from(expected);
  if (
    receivedBuffer.length !== expectedBuffer.length ||
    !timingSafeEqual(receivedBuffer, expectedBuffer)
  ) {
    return null;
  }
  try {
    const parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    return resolveSessionUser(parsed, { allowGuest: false });
  } catch {
    return null;
  }
}
