import { createOpenAI } from "@ai-sdk/openai";
import { streamText, jsonSchema, tool, wrapLanguageModel } from "ai";
import { promptionMiddleware } from "../../../../lib/ai/promptionMiddleware.js";
import { trustedAIRequest } from "../../../../lib/ai/trusted.js";
import { aiFailure } from "../../../../lib/ai/errors.mjs";

export const maxDuration = 300;
export const runtime = "nodejs";

function transcript(messages) {
  const names = new Map();
  return messages.map(message => {
    if (message.role === "user") {
      return { role: "user", content: String(message.content || "") };
    }
    if (message.role === "assistant") {
      const calls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
      const parts = [];
      if (message.content) parts.push({ type: "text", text: String(message.content) });
      for (const call of calls) {
        const toolName = call.function?.name;
        const toolCallId = call.id;
        names.set(toolCallId, toolName);
        parts.push({ type: "tool-call", toolCallId, toolName,
          input: JSON.parse(call.function?.arguments || "{}") });
      }
      return { role: "assistant", content: parts.length ? parts : "" };
    }
    if (message.role === "tool") {
      const toolCallId = message.tool_call_id;
      const toolName = names.get(toolCallId);
      if (!toolName) throw new Error("Resultado de herramienta sin llamada asociada");
      let value;
      try { value = JSON.parse(message.content || "{}"); }
      catch { value = { text: String(message.content || "") }; }
      return { role: "tool", content: [{ type: "tool-result", toolCallId, toolName,
        output: { type: "json", value } }] };
    }
    throw new Error("Rol de mensaje no admitido");
  });
}

export async function POST(request) {
  if (!trustedAIRequest(request)) return Response.json({ error: "No autorizado" }, { status: 401 });
  if (!process.env.OPENAI_API_KEY || !process.env.OPENAI_MODEL || !process.env.OPENAI_TOOL_MODEL) {
    return Response.json({ error: "Configuración de OpenAI incompleta en Next.js" }, { status: 503 });
  }
  let body;
  try { body = await request.json(); }
  catch { return Response.json({ error: "JSON inválido" }, { status: 400 }); }
  if (![process.env.OPENAI_MODEL, process.env.OPENAI_TOOL_MODEL].includes(body.model)
      || !Array.isArray(body.messages) || body.messages.length > 40
      || typeof body.original_text !== "string" || !body.original_text.trim()
      || typeof body.user_id !== "string" || !Array.isArray(body.roles)
      || body.roles.some(role => !["guest", "customer", "ventas", "admin"].includes(role))
      || !Array.isArray(body.tools) || body.tools.length > 25
      || (body.security_messages !== undefined && (!Array.isArray(body.security_messages)
          || body.security_messages.length > 128))) {
    return Response.json({ error: "Solicitud de modelo inválida" }, { status: 400 });
  }
  try {
    const provider = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const identity = { userId: body.user_id, roles: body.roles, authenticated: body.authenticated === true };
    const model = wrapLanguageModel({
      model: provider(body.model, /^gpt-5(?:-(?:nano|mini))?(?:-\d{4}-\d{2}-\d{2})?$/.test(body.model)
        ? { reasoningEffort: "minimal" } : {}),
      middleware: promptionMiddleware(identity, body.original_text, request.signal, body.security_messages,
        provider(process.env.OPENAI_MODEL, { reasoningEffort: 'minimal' })),
    });
    const tools = Object.fromEntries(body.tools.map(spec => [
      spec.function.name,
      tool({ description: spec.function.description,
        inputSchema: jsonSchema(spec.function.parameters) }),
    ]));
    const system = body.messages
      .filter(message => message.role === "system")
      .map(message => String(message.content || ""))
      .join("\n\n");
    const result = streamText({
      model,
      system,
      messages: transcript(body.messages.filter(message => message.role !== "system")),
      allowSystemInMessages: false,
      providerOptions: { openai: { parallelToolCalls: false, maxToolCalls: 1 } },
      tools,
      toolChoice: body.force_tool ? { type: "tool", toolName: body.force_tool } : "auto",
      maxOutputTokens: Math.min(Math.max(Number(body.max_tokens) || 1200, 100), 6000),
      abortSignal: request.signal,
    });
    const [text, toolCalls, finishReason] = await Promise.all([
      result.text, result.toolCalls, result.finishReason,
    ]);
    if (!text.trim() && !toolCalls.length) {
      console.warn("AI turn returned no usable output", { model: body.model, finishReason });
      return Response.json({ error: "El modelo no produjo una respuesta", code: "MODEL_EMPTY_RESPONSE" }, { status: 503 });
    }
    return Response.json({
      text,
      calls: toolCalls.map(call => ({
        id: call.toolCallId,
        name: call.toolName,
        arguments: JSON.stringify(call.input),
      })),
      model: body.model,
    });
  } catch (error) {
    const { code, status, reason, scope } = aiFailure(error);
    console.warn("AI turn failed", { code, status, model: body.model,
      guardReason: reason, scopeReason: scope?.reason,
      errorType: error.name, providerStatus: error.statusCode });
    return Response.json({ error: status === 403 ? "Promption bloqueó la respuesta" : "No se pudo generar la respuesta",
      code, ...(reason ? { reason } : {}), ...(scope ? { scope } : {}) }, { status });
  }
}
