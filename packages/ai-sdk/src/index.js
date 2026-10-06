import { conversationEvidence } from "./conversation.js";
import { PromptionError } from "./errors.js";
import { createFilterApiTransport } from "./transports.js";
import { validateScopeDecision, validateScopeRequest } from "./scope.js";
export { createScopeEvaluator } from "./scope.js";
export { PromptionError } from "./errors.js";
export { createFilterApiTransport, createGuardEndpointTransport } from "./transports.js";

const serialize = value => typeof value === "string" ? value : JSON.stringify(value);

function identityOf(identity) {
  if (!identity || typeof identity.userId !== "string" || !identity.userId
      || !Array.isArray(identity.roles) || identity.roles.some(role => typeof role !== "string")) {
    throw new TypeError("A server-resolved userId and roles array are required");
  }
  return { ...identity, roles: [...identity.roles] };
}

function permitted(name, identity, policies) {
  if (identity.authenticated !== true || identity.roles.includes("guest")) return false;
  if (!policies || !Object.hasOwn(policies, name)) return false;
  const policy = policies[name];
  if (!policy) return false;
  return !policy.roles?.length || policy.roles.some(role => identity.roles.includes(role));
}

function assertTool(name, identity, policies, tools) {
  if (!permitted(name, identity, policies)
      || (tools && !tools.some(tool => tool.name === name))) {
    throw new PromptionError("TOOL_ACCESS_DENIED");
  }
}

function textOf(message) {
  if (typeof message?.content === "string") return message.content;
  return (message?.content ?? []).filter(part => part.type === "text")
    .map(part => part.text).join("\n");
}

function cleanMetadata(result) {
  const { request, response, providerMetadata, ...rest } = result;
  return { ...rest, ...(response ? { response: {
    id: response.id, timestamp: response.timestamp, modelId: response.modelId,
  } } : {}) };
}

export function createPromption(config) {
  const transport = config.transport ?? createFilterApiTransport(config);
  for (const limit of [config.maxConversationMessages ?? 128, config.maxConversationChars ?? 100000]) {
    if (!Number.isSafeInteger(limit) || limit < 1) throw new TypeError("Conversation limits must be positive integers");
  }

  async function checkScope(text, options) {
    if (typeof config.scopeEvaluator !== "function") throw new TypeError("Configure a semantic scope evaluator");
    const request = { ...options, text, identity: identityOf(options.identity) };
    validateScopeRequest(request);
    options.signal?.throwIfAborted();
    let decision;
    try { decision = validateScopeDecision(await config.scopeEvaluator(request)); }
    catch (error) {
      if (options.signal?.aborted) throw error;
      decision = { classification: "UNCERTAIN", reason: "scope_unavailable", allowed: false, status: 503 };
    }
    options.signal?.throwIfAborted();
    config.onDecision?.({ direction: "input", allowed: decision.allowed,
      action: decision.allowed ? "PASS" : "BLOCK", userId: request.identity.userId, scope: decision });
    return decision;
  }

  async function enforceScope(text, options) {
    const decision = await checkScope(text, options);
    if (!decision.allowed) {
      const error = new PromptionError(decision.classification === "OUT_OF_SCOPE" ? "OUT_OF_SCOPE" : "SCOPE_UNCERTAIN",
        { status: decision.status, direction: "input" });
      error.scope = decision;
      throw error;
    }
  }
  const maxTextChars = config.maxTextChars ?? 100000;
  const maxStreamBytes = config.maxStreamBytes ?? 1048576;
  const earlyOutputCheckChars = config.earlyOutputCheckChars ?? 256;
  if (typeof transport !== "function" || !Number.isFinite(maxTextChars) || maxTextChars < 1
      || !Number.isFinite(maxStreamBytes) || maxStreamBytes < 1
      || !Number.isSafeInteger(earlyOutputCheckChars) || earlyOutputCheckChars < 1) {
    throw new TypeError("A guard transport and positive buffer limits are required");
  }

  async function check(text, options) {
    if (!["input", "output"].includes(options.direction)) throw new TypeError("Guard direction must be input or output");
    const identity = identityOf(options.identity);
    if (typeof text !== "string" || text.length > maxTextChars) {
      throw new PromptionError("CONTENT_TOO_LARGE", { direction: options.direction });
    }
    if (!text) return text;
    options.signal?.throwIfAborted();
    let result;
    try { result = await transport({ ...options, text, identity }); }
    catch (error) {
      if (error instanceof PromptionError || options.signal?.aborted) throw error;
      throw new PromptionError("GUARD_UNAVAILABLE", { status: 503, direction: options.direction, cause: error });
    }
    if (typeof result?.allowed !== "boolean" || (result.allowed && typeof result.text !== "string")) {
      throw new PromptionError("INVALID_GUARD_RESPONSE", { status: 503, direction: options.direction });
    }
    config.onDecision?.({ direction: options.direction, allowed: result.allowed,
      action: result.action, userId: identity.userId });
    if (!result.allowed) throw new PromptionError("CONTENT_BLOCKED", { direction: options.direction });
    return result.text;
  }

  function middleware(options) {
    const identity = identityOf(options.identity);
    const guard = (text, direction, params) => check(text, {
      identity, direction, signal: options.signal ?? params?.abortSignal, context: options.context,
    });
    const evidence = params => conversationEvidence(params?.prompt ?? [], options.securityMessages,
      { maxMessages: config.maxConversationMessages, maxChars: config.maxConversationChars });
    const scopeGuard = async (params, tool) => {
      if (!config.scopeEvaluator) return;
      const systemPrompt = options.systemPrompt ?? (params?.prompt ?? [])
        .filter(message => message.role === "system").map(textOf).join("\n\n");
      const lastText = textOf((params?.prompt ?? []).filter(message => message.role === "user").at(-1));
      const texts = new Set([options.originalText ?? lastText, ...(lastText ? [lastText] : [])]);
      for (const text of texts) {
        await enforceScope(text, { identity, systemPrompt, messages: evidence(params), tool,
          signal: options.signal ?? params?.abortSignal });
      }
    };
    const conversationGuard = async (text, params, extra = []) => {
      const messages = [...evidence(params), ...extra];
      if (!messages.length) return;
      const original = text || " ";
      const safe = await check(original, { identity, direction: "input",
        signal: options.signal ?? params?.abortSignal, context: options.context, messages });
      if (safe !== original) throw new PromptionError("CONVERSATION_REDACTED");
    };
    async function content(parts, params) {
      const checked = [];
      const texts = parts.filter(part => part.type === "text");
      const safeText = await guard(texts.map(part => part.text).join("\n"), "output", params);
      let textEmitted = false;
      for (const part of parts) {
        if (part.type === "text") {
          checked.push({ ...part, text: textEmitted ? "" : safeText, providerMetadata: undefined });
          textEmitted = true;
        } else if (part.type === "reasoning") {
          if (options.includeReasoning) checked.push({ ...part,
            text: await guard(part.text, "output", params), providerMetadata: undefined });
        } else if (part.type === "tool-call") {
          assertTool(part.toolName, identity, options.toolPolicies, params?.tools);
          await conversationGuard(part.input, params, [{ role: "tool", content: part.input, tool_name: part.toolName }]);
          await scopeGuard(params, { name: part.toolName, input: part.input,
            description: params?.tools?.find(tool => tool.name === part.toolName)?.description });
          const safe = await guard(part.input, "output", params);
          if (safe !== part.input) throw new PromptionError("TOOL_ARGUMENTS_REDACTED");
          checked.push({ ...part, providerMetadata: undefined });
        } else if (part.type === "file") {
          throw new PromptionError("UNINSPECTED_MODEL_FILE");
        } else {
          const original = serialize(part);
          if (await guard(original, "output", params) !== original) {
            throw new PromptionError("STRUCTURED_OUTPUT_REDACTED");
          }
          checked.push({ ...part, providerMetadata: undefined });
        }
      }
      return checked;
    }

    return {
      specificationVersion: "v3",
      transformParams: async ({ params }) => {
        const users = params.prompt.filter(message => message.role === "user");
        const original = options.originalText ?? textOf(users.at(-1));
        const safe = await guard(original, "input", params);
        const lastText = textOf(users.at(-1));
        const safeLast = lastText === original ? safe : await guard(lastText, "input", params);
        const prompt = params.prompt.map(message => {
          if (message !== users.at(-1) || lastText === safeLast) return message;
          return { ...message, content: [{ type: "text", text: safeLast }] };
        });
        for (const message of prompt) {
          const untrusted = message.role === "tool" ? message.content
            : message.role === "assistant" && Array.isArray(message.content)
              ? message.content.filter(part => part.type === "tool-result") : [];
          if (untrusted.length) {
            const raw = serialize(untrusted);
            if (await guard(raw, "input", params) !== raw) throw new PromptionError("UNTRUSTED_TOOL_CONTENT");
          }
        }
        await conversationGuard(safeLast || safe, { ...params, prompt });
        await scopeGuard({ ...params, prompt });
        const tools = params.tools?.filter(tool => permitted(tool.name, identity, options.toolPolicies));
        if (params.toolChoice?.type === "tool") {
          assertTool(params.toolChoice.toolName, identity, options.toolPolicies, tools);
        }
        return { ...params, prompt, tools };
      },
      wrapGenerate: async ({ doGenerate, params }) => {
        const result = await doGenerate();
        return { ...cleanMetadata(result), content: await content(result.content, params) };
      },
      wrapStream: async ({ doStream, params }) => {
        const result = await doStream();
        const reader = result.stream.getReader();
        const signal = options.signal ?? params?.abortSignal;
        let cancelled = false;
        const abort = () => { cancelled = true; void reader.cancel(signal.reason); };
        signal?.addEventListener("abort", abort, { once: true });
        const stream = new ReadableStream({
          start(controller) {
            void (async () => {
              const chunks = [];
              let bytes = 0;
              let generatedText = "";
              let nextOutputCheck = earlyOutputCheckChars;
              while (!cancelled) {
                signal?.throwIfAborted();
                const { value, done } = await reader.read();
                if (done) break;
                bytes += new TextEncoder().encode(serialize(value)).byteLength;
                if (bytes > maxStreamBytes) throw new PromptionError("STREAM_TOO_LARGE");
                if (value.type === "error") throw new PromptionError("MODEL_STREAM_FAILED", { status: 503 });
                chunks.push(value);
                if (value.type === "text-delta") {
                  generatedText += value.delta;
                  if (generatedText.length >= nextOutputCheck) {
                    const checked = await guard(generatedText, "output", params);
                    if (checked !== generatedText) {
                      throw new PromptionError("CONTENT_BLOCKED", { direction: "output" });
                    }
                    nextOutputCheck = generatedText.length + earlyOutputCheckChars;
                  }
                }
              }
              signal?.throwIfAborted();
              if (cancelled) return;
              const safe = await guard(generatedText, "output", params);
              const complete = chunks.filter(chunk => ["tool-call", "tool-result", "source", "file", "tool-approval-request"].includes(chunk.type));
              await content(complete, params);
              const reasoning = chunks.filter(chunk => chunk.type === "reasoning-delta");
              const safeReasoning = options.includeReasoning
                ? await guard(reasoning.map(chunk => chunk.delta).join(""), "output", params) : "";
              let emitted = false, reasoningEmitted = false;
              for (const chunk of chunks) {
                if (cancelled) return;
                if (chunk.type === "raw" || chunk.type.startsWith("tool-input-")) continue;
                if (chunk.type.startsWith("reasoning-") && !options.includeReasoning) continue;
                const { providerMetadata, ...clean } = chunk;
                if (chunk.type === "text-delta") {
                  clean.delta = emitted ? "" : safe; emitted = true;
                }
                if (chunk.type === "reasoning-delta") {
                  clean.delta = reasoningEmitted ? "" : safeReasoning; reasoningEmitted = true;
                }
                controller.enqueue(clean);
              }
              controller.close();
            })().catch(async error => {
              await reader.cancel(error).catch(() => {});
              if (!cancelled || signal?.aborted) controller.error(error);
            }).finally(() => {
              signal?.removeEventListener("abort", abort);
              reader.releaseLock();
            });
          },
          async cancel(reason) { cancelled = true; await reader.cancel(reason); },
        });
        return { ...cleanMetadata(result), stream };
      },
    };
  }

  function protectTool(definition, options) {
    const identity = identityOf(options.identity);
    if (typeof definition.execute !== "function") throw new TypeError("An executable AI SDK/MCP tool is required");
    return {
      ...definition,
      execute: async (input, execution) => {
        assertTool(options.name, identity, options.policy ? { [options.name]: options.policy } : undefined);
        const signal = options.signal ?? execution?.abortSignal;
        const raw = serialize(input);
        if (await check(raw, { direction: "input", identity, signal }) !== raw) {
          throw new PromptionError("TOOL_ARGUMENTS_REDACTED");
        }
        const messages = conversationEvidence(execution?.messages ?? [], options.securityMessages,
          { maxMessages: config.maxConversationMessages, maxChars: config.maxConversationChars });
        if (messages.length) {
          const safe = await check(raw, { direction: "input", identity, signal,
            messages: [...messages, { role: "tool", content: raw, tool_name: options.name }] });
          if (safe !== raw) throw new PromptionError("TOOL_ARGUMENTS_REDACTED");
        }
        if (config.scopeEvaluator) {
          const lastText = messages.filter(message => message.role === "user").at(-1)?.content;
          const texts = new Set([options.originalText ?? lastText, ...(lastText ? [lastText] : [])]);
          for (const text of texts) {
            await enforceScope(text, { identity, signal, systemPrompt: options.systemPrompt, messages,
              tool: { name: options.name, input: raw, description: definition.description } });
          }
        }
        const result = await definition.execute(input, execution);
        const original = serialize(result);
        const safe = await check(original, { direction: "output", identity, signal });
        if (safe === original) return result;
        if (typeof result === "string") return safe;
        try { return JSON.parse(safe); }
        catch { throw new PromptionError("STRUCTURED_OUTPUT_REDACTED"); }
      },
    };
  }

  return Object.freeze({ check, checkScope, middleware, protectTool });
}
