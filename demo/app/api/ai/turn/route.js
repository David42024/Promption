import { createTrackingModel } from "../../../../lib/ai/tracking.js";
import { createOpenAI } from "@ai-sdk/openai";
import { streamText, jsonSchema, tool, wrapLanguageModel } from "ai";
import { promptionMiddleware } from "../../../../lib/ai/promptionMiddleware.js";
import { trustedAIRequest } from "../../../../lib/ai/trusted.js";
import { aiFailure } from "../../../../lib/ai/errors.mjs";
import { getModelProviderOptions, validateModelConfiguration } from "../../../../lib/ai/modelOptions.js";
import { MetricsAggregator } from "../../../../lib/ai/metrics.js";

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
    return Response.json({
      error: "Cancelado",
      code: "CANCELLED",
      provider_calls: 0,
      scope_calls: 0,
      generation_calls: 0,
      usage: null,
      known_usage: { prompt_tokens: null, completion_tokens: null, total_tokens: null, reasoning_tokens: null },
      usage_coverage: { calls_total: 0, calls_with_usage: 0, calls_without_usage: 0, is_complete: true, fields: { prompt_tokens: true, completion_tokens: true, total_tokens: true, reasoning_tokens: true } },
      request_id: requestId,
    }, { status: 499, headers: { "x-request-id": requestId } });
  } else {
    request.signal?.addEventListener("abort", abortFromRequest, { once: true });
  }
  const timeoutMs = Number(body.timeout_ms) > 0 ? Number(body.timeout_ms)
    : (Number(body.timeout_seconds) > 0 ? Number(body.timeout_seconds) * 1000 : null);
  const timer = timeoutMs ? setTimeout(() => {
    controller.abort(new DOMException("The operation timed out.", "TimeoutError"));
  }, timeoutMs) : null;

  const scopeReceipts = [];
  let scopeCalls = 0;
  let generationCalls = 0;
  const aggregator = new MetricsAggregator();
  const onScope = (decision) => {
    const u = decision?.usage;
    const hasUsage = Boolean(u && (
      typeof u.prompt_tokens === "number" ||
      typeof u.completion_tokens === "number" ||
      typeof u.total_tokens === "number" ||
      typeof u.reasoning_tokens === "number"
    ));
    aggregator.addCall({
      callType: "scope",
      calls: decision?.provider_calls === 0 ? 0 : 1,
      promptTokens: typeof u?.prompt_tokens === "number" ? u.prompt_tokens : null,
      completionTokens: typeof u?.completion_tokens === "number" ? u.completion_tokens : null,
      totalTokens: typeof u?.total_tokens === "number" ? u.total_tokens : null,
      reasoningTokens: typeof u?.reasoning_tokens === "number" ? u.reasoning_tokens : null,
      hasUsage,
      eventId: `scope-${aggregator.scopeCalls + 1}`,
    });
  };

  try {
    const provider = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const identity = { userId: body.user_id, roles: body.roles, authenticated: body.authenticated === true };
    const scopeModelId = process.env.OPENAI_MODEL;
    const scopeProviderOptions = getModelProviderOptions(scopeModelId);
    const trackingScopeModel = createTrackingModel(provider(scopeModelId), () => { scopeCalls++; });
    const trackingGenerationModel = createTrackingModel(provider(body.model), () => { generationCalls++; });
    const model = wrapLanguageModel({
      model: trackingGenerationModel,
      middleware: promptionMiddleware(identity, body.original_text, controller.signal, body.security_messages,
        trackingScopeModel, scopeProviderOptions, { onScope,
          scopeReceipts: body.scope_receipts, scopeBinding: body.scope_binding, scopeModelId, requestId,
          onScopeReceipt: receipt => { if (scopeReceipts.length < 32) scopeReceipts.push(receipt); },
          systemPrompt: body.scope_system_prompt || undefined }),
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
    let text, toolCalls, finishReason, rawUsage;
    try {
      [text, toolCalls, finishReason, rawUsage] = await Promise.all([
        result.text, result.toolCalls, result.finishReason,
        Promise.resolve(result.usage).catch(() => null),
      ]);
    } catch (err) {
      throw (streamError || err);
    }

    // Account for any scope calls tracked but not in aggregator
    while (aggregator.scopeCalls < scopeCalls) {
      aggregator.addCall({ callType: "scope", calls: 1, hasUsage: false });
    }

    if (generationCalls > 0) {
      const inputTok = rawUsage?.inputTokens ?? rawUsage?.promptTokens ?? null;
      const outputTok = rawUsage?.outputTokens ?? rawUsage?.completionTokens ?? null;
      const totalTok = rawUsage?.totalTokens ?? null;
      const reasoningTok = rawUsage?.outputTokenDetails?.reasoningTokens ?? rawUsage?.reasoningTokens ?? null;
      const hasUsage = Boolean(rawUsage && (
        typeof inputTok === "number" ||
        typeof outputTok === "number" ||
        typeof totalTok === "number" ||
        typeof reasoningTok === "number"
      ));
      aggregator.addCall({
        callType: "generation",
        calls: generationCalls,
        promptTokens: typeof inputTok === "number" ? inputTok : null,
        completionTokens: typeof outputTok === "number" ? outputTok : null,
        totalTokens: typeof totalTok === "number" ? totalTok : null,
        reasoningTokens: typeof reasoningTok === "number" ? reasoningTok : null,
        hasUsage,
        eventId: "generation-turn",
      });
    }

    const summary = aggregator.summary();
    const usage = summary.provider_calls > 0 ? {
      prompt_tokens: summary.prompt_tokens,
      completion_tokens: summary.completion_tokens,
      total_tokens: summary.total_tokens,
      reasoning_tokens: summary.reasoning_tokens,
    } : null;

    if (!text.trim() && !toolCalls.length) {
      console.warn("AI turn returned no usable output", { model: body.model, finishReason });
      if (finishReason === "length") {
        return Response.json({
          error: "Respuesta del modelo truncada por límite de tokens",
          code: "MODEL_RESPONSE_TRUNCATED",
          provider_calls: summary.provider_calls,
          scope_calls: summary.scope_calls,
          generation_calls: summary.generation_calls,
          usage,
          known_usage: summary.known_usage,
          usage_coverage: summary.usage_coverage,
        }, { status: 502, headers: { "x-request-id": requestId } });
      }
      return Response.json({
        error: "El modelo no produjo una respuesta",
        code: "MODEL_EMPTY_RESPONSE",
        provider_calls: summary.provider_calls,
        scope_calls: summary.scope_calls,
        generation_calls: summary.generation_calls,
        usage,
        known_usage: summary.known_usage,
        usage_coverage: summary.usage_coverage,
      }, { status: 503, headers: { "x-request-id": requestId } });
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
      scope_receipts: scopeReceipts,
      provider_calls: summary.provider_calls,
      scope_calls: summary.scope_calls,
      generation_calls: summary.generation_calls,
      usage,
      known_usage: summary.known_usage,
      usage_coverage: summary.usage_coverage,
    }, {
      headers: { "x-request-id": requestId },
    });
  } catch (error) {
    const { code, status, reason, scope } = aiFailure(error, { signal: request.signal, aborted: request.signal?.aborted });
    console.warn("AI turn failed", { requestId, code, status, model: body.model,
      guardReason: reason, scopeReason: scope?.reason,
      errorType: error.name, providerStatus: error.statusCode });

    while (aggregator.scopeCalls < scopeCalls) {
      aggregator.addCall({ callType: "scope", calls: 1, hasUsage: false, failed: true });
    }
    if (generationCalls > 0 && aggregator.generationCalls < generationCalls) {
      aggregator.addCall({ callType: "generation", calls: generationCalls - aggregator.generationCalls, hasUsage: false, failed: true });
    }
    const errSummary = aggregator.summary();

    return Response.json({
      error: status === 403 ? "Promption bloqueó la respuesta" : "No se pudo generar la respuesta",
      code, ...(reason ? { reason } : {}), ...(scope ? { scope } : {}),
      provider_calls: errSummary.provider_calls,
      scope_calls: errSummary.scope_calls,
      generation_calls: errSummary.generation_calls,
      usage: null,
      known_usage: errSummary.known_usage,
      usage_coverage: errSummary.usage_coverage,
      request_id: requestId,
    }, { status, headers: { "x-request-id": requestId } });
  } finally {
    if (timer) clearTimeout(timer);
    request.signal?.removeEventListener("abort", abortFromRequest);
  }
}
