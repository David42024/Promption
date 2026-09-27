const CHAT_API_URL = (process.env.CHAT_API_URL || process.env.NEXT_PUBLIC_CHAT_API_URL || "").replace(/\/$/, "");

export async function checkPromption(text, identity, direction, signal) {
  const response = await fetch(`${CHAT_API_URL}/api/v1/ai/guard`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Chat-Service-Token": process.env.CHAT_SERVICE_TOKEN || "",
    },
    body: JSON.stringify({
      text,
      direction,
      user_id: identity.userId,
      roles: identity.roles,
    }),
    signal,
    cache: "no-store",
  });
  if (!response.ok) {
    const error = new Error("Promption bloqueó la llamada al modelo.");
    error.status = response.status === 403 ? 403 : 503;
    throw error;
  }
  const result = await response.json();
  if (!result.allowed || typeof result.text !== "string") {
    const error = new Error("Promption no autorizó el contenido.");
    error.status = 403;
    throw error;
  }
  return result.text;
}

export function promptionMiddleware(identity, originalText, signal) {
  return {
    specificationVersion: "v3",
    transformParams: async ({ params }) => {
      await checkPromption(originalText, identity, "input", signal);
      return params;
    },
    wrapGenerate: async ({ doGenerate }) => {
      const result = await doGenerate();
      const text = result.content.filter(part => part.type === "text").map(part => part.text).join("");
      if (!text) return result;
      const guarded = await checkPromption(text, identity, "output", signal);
      if (guarded === text) return result;
      let replaced = false;
      return {
        ...result,
        content: result.content.map(part => {
          if (part.type !== "text") return part;
          if (replaced) return { ...part, text: "" };
          replaced = true;
          return { ...part, text: guarded };
        }),
      };
    },
  };
}
