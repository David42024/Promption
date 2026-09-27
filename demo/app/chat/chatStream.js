export async function sendChat(text, onStatus, signal) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!response.ok) {
    return { ok: false, data: await response.json().catch(() => ({ error: "Error del chat" })) };
  }
  if (!response.body) throw new Error("El servidor no envió una respuesta.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const line = frame.split("\n").find(part => part.startsWith("data: "));
        if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === "status") onStatus(event.stage);
        if (event.type === "result") result = event.data;
        if (event.type === "error") throw new Error(event.message || "Error del chat");
      }
      if (result) break;
      if (done) throw new Error("La respuesta terminó antes de completarse.");
    }
  } finally {
    reader.releaseLock();
  }
  return { ok: true, data: result };
}
