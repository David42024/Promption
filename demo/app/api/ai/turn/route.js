import { createOpenAI } from "@ai-sdk/openai";
import { streamText, jsonSchema, tool, wrapLanguageModel } from "ai";
import { promptionMiddleware } from "../../../../lib/ai/promptionMiddleware.js";
import { trustedAIRequest } from "../../../../lib/ai/trusted.js";
import { aiFailure } from "../../../../lib/ai/errors.mjs";
import { getModelProviderOptions, validateModelConfiguration } from "../../../../lib/ai/modelOptions.js";

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
  const requestId = request.headers.get("x-request-id") || body?.request_id || crypto.randomUUID();
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
  const controller = new AbortController();
  const abortFromRequest = () => controller.abort(request.signal.reason);
  if (request.signal?.aborted) {
    controller.abort(request.signal.reason);
  } else {
    request.signal?.addEventListener("abort", abortFromRequest, { once: true });
  }
  const timeoutMs = Number(body.timeout_ms) > 0 ? Number(body.timeout_ms)
    : (Number(body.timeout_seconds) > 0 ? Number(body.timeout_seconds) * 1000 : null);
  const timer = timeoutMs ? setTimeout(() => {
    controller.abort(new DOMException("The operation timed out.", "TimeoutError"));
  }, timeoutMs) : null;

  try {
    const provider = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const identity = { userId: body.user_id, roles: body.roles, authenticated: body.authenticated === true };
    const scopeModelId = process.env.OPENAI_MODEL;
    const scopeProviderOptions = getModelProviderOptions(scopeModelId);
    const model = wrapLanguageModel({
      model: provider(body.model),
      middleware: promptionMiddleware(identity, body.original_text, controller.signal, body.security_messages,
        provider(scopeModelId), scopeProviderOptions),
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
    const hasTools = Object.keys(tools).length > 0;
    let streamError = null;
    const result = streamText({
      model,
      system,
      messages: transcript(body.messages.filter(message => message.role !== "system")),
      allowSystemInMessages: false,
      providerOptions: getModelProviderOptions(body.model, { parallelToolCalls: false, maxToolCalls: 1 }),
      ...(hasTools ? { tools } : {}),
      toolChoice: body.force_tool ? { type: "tool", toolName: body.force_tool } : (hasTools ? "auto" : "none"),
      maxOutputTokens: Math.min(Math.max(Number(body.max_tokens) || 1200, 100), 6000),
      maxRetries: 0,
      abortSignal: controller.signal,
      onError({ error }) {
        streamError = error;
      },
    });
    let text, toolCalls, finishReason;
    try {
      [text, toolCalls, finishReason] = await Promise.all([
        result.text, result.toolCalls, result.finishReason,
      ]);
    } catch (err) {
      throw (streamError || err);
    }
    if (!text.trim() && !toolCalls.length) {
      console.warn("AI turn returned no usable output", { model: body.model, finishReason });
      if (finishReason === "length") {
        return Response.json({ error: "Respuesta del modelo truncada por límite de tokens", code: "MODEL_RESPONSE_TRUNCATED" }, { status: 502 });
      }
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
      finish_reason: finishReason,
      truncated: finishReason === "length",
      request_id: requestId,
    }, {
      headers: { "x-request-id": requestId },
    });
  } catch (error) {
    const { code, status, reason, scope } = aiFailure(error, { signal: request.signal, aborted: request.signal?.aborted });
    console.warn("AI turn failed", { code, status, model: body.model,
      guardReason: reason, scopeReason: scope?.reason,
      errorType: error.name, providerStatus: error.statusCode });
    return Response.json({ error: status === 403 ? "Promption bloqueó la respuesta" : "No se pudo generar la respuesta",
      code, ...(reason ? { reason } : {}), ...(scope ? { scope } : {}) }, { status });
  } finally {
    if (timer) clearTimeout(timer);
    request.signal?.removeEventListener("abort", abortFromRequest);
  }
}
