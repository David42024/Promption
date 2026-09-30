import { createPromption, createGuardEndpointTransport } from "@promption/ai-sdk";

const CHAT_API_URL = (process.env.CHAT_API_URL || process.env.NEXT_PUBLIC_CHAT_API_URL || "").replace(/\/$/, "");

function promption() {
  return createPromption({
    transport: createGuardEndpointTransport({
      url: `${CHAT_API_URL}/api/v1/ai/guard`, token: process.env.CHAT_SERVICE_TOKEN,
      timeoutMs: 60000,
    }),
  });
}

export function promptionMiddleware(identity, originalText, signal, securityMessages) {
  return promption().middleware({ identity, originalText, signal, securityMessages });
}

export function checkPromption(text, identity, direction, signal) {
  return promption().check(text, { identity, direction, signal });
}
