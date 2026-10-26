import { conversationEvidence } from "./conversation.js";
import { PromptionError } from "./errors.js";
import { createFilterApiTransport } from "./transports.js";
import { resolveProtection } from './profiles.js';
export { resolveProtection } from './profiles.js';
import { validateScopeDecision, validateScopeRequest, needsClarification, clarificationText, missingReference, missingReferenceDecision } from "./scope.js";
import { assess, emptyAssessments, validateAssessments } from './assessments.js';
import { compileKnownValues, matchKnownValue } from './known-values.js';
import { createToolSignatureStore } from './provider-signatures.js';
export { createScopeEvaluator } from "./scope.js";
export { createContextEvaluator } from "./context.js";
export { PromptionError } from "./errors.js";
export { createFilterApiTransport, createGuardEndpointTransport } from "./transports.js";
export { MetricsAggregator } from "./metrics.js";

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
  const protection = resolveProtection(config.protection);
  const protectedValues = compileKnownValues(config.protectedValues);
  const emit = event => config.onDecision?.({ assessments: emptyAssessments(), ...event, protection });
  const authorizeTool = (name, identity, policies, tools) => {
    try {
      assertTool(name, identity, policies, tools);
      emit({ direction: 'input', control: 'authorization', allowed: true, action: 'PASS', userId: identity.userId,
        assessments: assess(null, 'authorization', 'allowed', 'policy_allowed', 'tool_policy') });
    }
    catch (error) {
      emit({ direction: 'input', control: 'authorization', allowed: false, action: 'BLOCK',
        reason: 'tool_access_denied', userId: identity.userId,
        assessments: assess(null, 'authorization', 'denied', 'tool_access_denied', 'tool_policy') });
      throw error;
    }
  };
  const transport = config.transport ?? createFilterApiTransport(config);
  const isolationReceipts = new Map();
  const identityKey = identity => JSON.stringify([identity.userId, [...identity.roles].sort(), identity.authenticated === true]);
  const rememberIsolation = (receipt, identity) => {
    const key = JSON.stringify([identityKey(identity), receipt]);
    isolationReceipts.set(key, { ...receipt, identity: identityKey(identity) });
    if (isolationReceipts.size > 32) isolationReceipts.delete(isolationReceipts.keys().next().value);
  };
  const focusedToolEvidence = (messages, identity, current) => {
    for (const receipt of isolationReceipts.values()) {
      if (receipt.identity === identityKey(identity) && receipt.current === current
          && messages.findLastIndex(message => message.role === 'user') === receipt.prefix.length
          && receipt.prefix.every((message, index) => JSON.stringify(message) === JSON.stringify(messages[index]))
          && messages[receipt.prefix.length]?.role === 'user'
          && messages[receipt.prefix.length].content === current) return messages.slice(receipt.prefix.length);
    }
    return messages;
  };
  for (const limit of [config.maxConversationMessages ?? 128, config.maxConversationChars ?? 100000]) {
    if (!Number.isSafeInteger(limit) || limit < 1) throw new TypeError("Conversation limits must be positive integers");
  }

  async function checkScope(text, options) {
    const missing = missingReference(text, options.messages);
    if (typeof config.scopeEvaluator !== "function" && !missing) throw new TypeError("Configure a semantic scope evaluator");
    const request = { ...options, text, identity: identityOf(options.identity) };
    validateScopeRequest(request);
    options.signal?.throwIfAborted();
    let decision;
    try { decision = missing && typeof config.scopeEvaluator !== 'function' ? missingReferenceDecision()
      : validateScopeDecision(await config.scopeEvaluator(request)); }
    catch (error) {
      if (options.signal?.aborted) throw error;
      const timedOut = error?.name === "TimeoutError" || error?.name === "AbortError";
      decision = validateScopeDecision({ classification: "UNCERTAIN", reason: timedOut ? "scope_timeout" : "scope_unavailable" });
    }
    options.signal?.throwIfAborted();
    emit({ direction: "input", control: decision.control ?? (decision.status >= 500 ? 'operational' : 'scope'), allowed: decision.allowed,
      action: decision.allowed ? "PASS" : decision.classification === 'UNCERTAIN'
        ? decision.status >= 500 || decision.control === 'operational' ? 'ERROR' : 'REVIEW' : "BLOCK", userId: request.identity.userId, scope: decision,
      assessments: decision.assessments });
    if (typeof config.onScope === "function") {
      config.onScope(decision);
    }
    if (typeof options.onScope === "function" && options.onScope !== config.onScope) {
      options.onScope(decision);
    }
    return decision;
  }

  async function enforceScope(text, options, allowClarification = false) {
    const decision = await checkScope(text, options);
    if (!decision.allowed) {
      if (allowClarification && needsClarification(decision, options.tool, protection)) return decision;
      const error = new PromptionError(decision.classification === "OUT_OF_SCOPE" ? "OUT_OF_SCOPE" : "SCOPE_UNCERTAIN",
        { status: decision.status, direction: "input", reason: decision.reason,
          control: decision.control ?? (decision.status >= 500 ? 'operational' : 'scope') });
      error.scope = decision;
      throw error;
    }
    return decision;
  }
  const maxTextChars = config.maxTextChars ?? 100000;
  const maxStreamBytes = config.maxStreamBytes ?? 1048576;
  const earlyOutputCheckChars = config.earlyOutputCheckChars ?? 256;
  if (typeof transport !== "function" || !Number.isFinite(maxTextChars) || maxTextChars < 1
      || !Number.isFinite(maxStreamBytes) || maxStreamBytes < 1
      || !Number.isSafeInteger(earlyOutputCheckChars) || earlyOutputCheckChars < 1) {
    throw new TypeError("A guard transport and positive buffer limits are required");
  }

  async function inspect(text, options) {
    if (!["input", "output"].includes(options.direction)) throw new TypeError("Guard direction must be input or output");
    const identity = identityOf(options.identity);
    if (typeof text !== "string" || text.length > maxTextChars) {
      throw new PromptionError("CONTENT_TOO_LARGE", { direction: options.direction });
    }
    if (!text) return { allowed: true, text };
    options.signal?.throwIfAborted();
    if (options.direction === 'output') {
      const policyReason = matchKnownValue(text, protectedValues);
      if (policyReason) {
        emit({ direction: 'output', control: 'output', allowed: false, action: 'BLOCK', reason: 'sensitive_output',
          policyReason, userId: identity.userId });
        throw new PromptionError('CONTENT_BLOCKED', { direction: 'output', control: 'output', reason: 'sensitive_output' });
      }
    }
    let result;
    try { result = await transport({ ...options, text, identity }); }
    catch (error) {
      if (error instanceof PromptionError || options.signal?.aborted) throw error;
      throw new PromptionError("GUARD_UNAVAILABLE", { status: 503, direction: options.direction, cause: error });
    }
    if (typeof result?.allowed !== "boolean" || (result.allowed && typeof result.text !== "string")) {
      throw new PromptionError("INVALID_GUARD_RESPONSE", { status: 503, direction: options.direction });
    }
    if (['requiresScopeReview', 'requiresOutputGuard'].some(key => result[key] !== undefined && typeof result[key] !== 'boolean')) {
      throw new PromptionError('INVALID_GUARD_RESPONSE', { status: 503, direction: options.direction });
    }
    const scores = [result.inputRiskScore, result.conversation?.input_risk_score];
    if (scores.some(score => score !== undefined && score !== null &&
        (typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > 1))) {
      throw new PromptionError('INVALID_GUARD_RESPONSE', { status: 503, direction: options.direction });
    }
    const inputRiskScore = Math.max(-1, ...scores.filter(score => typeof score === 'number'));
    if (result.allowed && ['BLOCK', 'BLOCKED'].includes(result.action)) {
      throw new PromptionError('INVALID_GUARD_RESPONSE', { status: 503, direction: options.direction });
    }
    let assessments;
    const legacyControl = ['scope', 'authorization'].includes(result.control) ? result.control : 'injection';
    try { assessments = result.assessments ? validateAssessments(result.assessments) : options.direction === 'input'
      ? assess(null, legacyControl, !result.allowed ? 'denied' : result.requiresOutputGuard || result.action === 'GUARDED' ? 'uncertain' : 'allowed',
        !result.allowed ? legacyControl === 'authorization' ? 'policy_denied' : legacyControl === 'scope' ? 'out_of_scope' : 'malicious_input'
          : result.requiresOutputGuard || result.action === 'GUARDED' ? 'review_required' : legacyControl === 'injection' ? 'no_attack_detected' : 'policy_allowed', 'guard_transport')
      : emptyAssessments(); }
    catch { throw new PromptionError('INVALID_GUARD_RESPONSE', { status: 503, direction: options.direction }); }
    if (result.allowed && options.direction === 'input' && inputRiskScore >= protection.reviewBlockThreshold) {
      assessments = assess(assessments, 'injection', 'uncertain', 'risk_policy_veto', 'profile_policy');
      emit({ direction: 'input', control: 'injection', allowed: false, action: 'BLOCK', reason: 'risk_policy_veto',
        userId: identity.userId, assessments });
      throw new PromptionError('INPUT_RISK_LIMIT', { direction: 'input', control: 'injection', reason: 'risk_policy_veto' });
    }
    if (result.allowed && options.direction === 'input' && result.requiresScopeReview === true && typeof config.scopeEvaluator !== 'function') {
      throw new PromptionError('SCOPE_REVIEW_REQUIRED', { status: 503, direction: 'input', control: 'operational' });
    }
    const control = result.control ?? (options.direction === 'output' ? 'output' : 'injection');
    if (!result.allowed) {
      emit({ direction: options.direction, allowed: false, control,
        action: result.action, userId: identity.userId, reason: result.reason, assessments });
      throw new PromptionError("CONTENT_BLOCKED", { direction: options.direction, control, reason: result.reason });
    }
    if (options.direction === 'input' && protection.inputUncertainty === 'block'
        && (result.requiresOutputGuard === true || result.action === 'GUARDED'
          || result.conversation?.requires_output_guard === true)) {
      emit({ direction: 'input', control: 'injection', allowed: false, action: 'BLOCK', reason: 'uncertain_input', userId: identity.userId });
      throw new PromptionError('INPUT_UNCERTAIN', { direction: 'input', control: 'injection', reason: 'uncertain_input' });
    }
    emit({ direction: options.direction, allowed: true, control,
      action: result.action, userId: identity.userId, reason: result.reason, assessments });
    return { ...result, assessments };
  }

  async function check(text, options) { return (await inspect(text, options)).text; }

  function middleware(options) {
    const identity = identityOf(options.identity);
    const providerSignatures = createToolSignatureStore();
    const turnCache = new Map();
    const receipts = [];
    const matchingIsolation = messages => receipts.findLast(receipt =>
      messages.findLastIndex(message => message.role === 'user') === receipt.prefix.length
      && receipt.prefix.every((message, index) => JSON.stringify(message) === JSON.stringify(messages[index]))
      && messages[receipt.prefix.length]?.role === 'user'
      && messages[receipt.prefix.length].content === receipt.current);
    const focus = messages => {
      const receipt = matchingIsolation(messages);
      return receipt ? messages.slice(receipt.prefix.length) : messages;
    };
    const guardKey = (text, direction, opts = {}) => JSON.stringify({
      t: text, d: direction, u: identity.userId, r: [...identity.roles].sort(), a: identity.authenticated,
      m: opts.messages ?? null, c: opts.context ?? options.context ?? null,
      isolated: opts.isolateHistory === true,
    });
    const cachedGuard = async (text, direction, params, extra = {}) => {
      const opts = { identity, direction, signal: options.signal ?? params?.abortSignal, context: options.context, ...extra };
      opts.signal?.throwIfAborted();
      const key = guardKey(text, direction, opts);
      if (turnCache.has(key)) return turnCache.get(key).text;
      const res = await inspect(text, opts);
      turnCache.set(key, res);
      return res.text;
    };
    const guard = (text, direction, params) => cachedGuard(text, direction, params);
    const fullEvidence = params => conversationEvidence(params?.prompt ?? [], options.securityMessages,
      { maxMessages: config.maxConversationMessages, maxChars: config.maxConversationChars });
    const evidence = params => focus(fullEvidence(params));
    const scopeKey = (text, systemPrompt, msgs, tool, format) => JSON.stringify({
      t: text, u: identity.userId, r: [...identity.roles].sort(), a: identity.authenticated,
      s: systemPrompt, m: msgs, tl: tool ?? null, f: format ?? null,
    });
    const scopeGuard = async (params, tool) => {
      (options.signal ?? params?.abortSignal)?.throwIfAborted();
      const systemPrompt = options.systemPrompt ?? (params?.prompt ?? [])
        .filter(message => message.role === "system").map(textOf).join("\n\n");
      const lastText = textOf((params?.prompt ?? []).filter(message => message.role === "user").at(-1));
      const texts = new Set([options.originalText ?? lastText, ...(lastText ? [lastText] : [])]);
      const ev = evidence(params);
      if (!config.scopeEvaluator && ![...texts].some(text => missingReference(text, ev))) return;
      let clarification;
      for (const text of texts) {
        const key = scopeKey(text, systemPrompt, ev, tool, params?.responseFormat?.type);
        let decision = turnCache.get(key);
        if (!decision) {
          decision = await enforceScope(text, { identity, systemPrompt: systemPrompt || 'Clarify missing context before any action.', messages: ev, tool,
            signal: options.signal ?? params?.abortSignal, onScope: options.onScope },
            !tool && params?.responseFormat?.type !== 'json');
          turnCache.set(key, decision);
        }
        if (needsClarification(decision, tool, protection)) clarification = decision;
      }
      return clarification;
    };
    const conversationGuard = async (text, params, extra = []) => {
      const full = fullEvidence(params);
      const previous = matchingIsolation(full);
      const messages = [...(previous ? full.slice(previous.prefix.length) : full), ...extra];
      if (!messages.length) return;
      const original = text || " ";
      const safe = await cachedGuard(original, "input", params, { messages, isolateHistory: true });
      if (safe !== original) throw new PromptionError("CONVERSATION_REDACTED");
      const key = guardKey(original, "input", { messages, isolateHistory: true });
      const result = turnCache.get(key);
      if (result?.conversation?.isolated_history === true) {
        if (extra.length || result.conversation.message_count !== messages.length
            || result.conversation.evaluation_mode !== 'independent_turn'
            || result.conversation.requires_output_guard !== true
            || messages.at(-1)?.role !== 'user' || messages.at(-1).content !== original) {
          throw new PromptionError('INVALID_GUARD_RESPONSE');
        }
        const receipt = { prefix: messages.slice(0, -1).map(message => ({ ...message })), current: original };
        receipts.push(receipt);
        rememberIsolation(receipt, identity);
        emit({ direction: 'input', control: 'injection', allowed: true, action: 'ISOLATE_HISTORY', userId: identity.userId });
        return receipt;
      }
      return previous;
    };
    const syntheticResult = async params => {
      if (!await scopeGuard(params)) return;
      const text = await guard(clarificationText, 'output', params);
      emit({ direction: 'input', control: 'scope', allowed: false, action: 'CLARIFY', userId: identity.userId });
      return { content: [{ type: 'text', text }], finishReason: { unified: 'stop', raw: 'clarification' },
        usage: { inputTokens: { total: 0 }, outputTokens: { total: 0 } }, warnings: [] };
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
          authorizeTool(part.toolName, identity, options.toolPolicies, params?.tools);
          await conversationGuard(part.input, params, [{ role: "tool", content: part.input, tool_name: part.toolName }]);
          await scopeGuard(params, { name: part.toolName, input: part.input,
            description: params?.tools?.find(tool => tool.name === part.toolName)?.description });
          const safe = await guard(part.input, "output", params);
          if (safe !== part.input) throw new PromptionError("TOOL_ARGUMENTS_REDACTED");
          providerSignatures.remember(part);
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
        const receipt = await conversationGuard(safeLast || safe, { ...params, prompt });
        const active = receipt ? prompt.filter(message => message.role === 'system')
          .concat(prompt.slice(prompt.findLastIndex(message => message.role === 'user'))) : prompt;
        const clarification = await scopeGuard({ ...params, prompt: active });
        if (clarification) return { ...params, prompt: active, tools: [], toolChoice: { type: 'none' } };
        const tools = params.tools?.filter(tool => permitted(tool.name, identity, options.toolPolicies));
        if (params.toolChoice?.type === "tool") {
          authorizeTool(params.toolChoice.toolName, identity, options.toolPolicies, tools);
        }
        return { ...params, prompt: providerSignatures.restore(active,
          name => permitted(name, identity, options.toolPolicies)), tools };
      },
      wrapGenerate: async ({ doGenerate, params }) => {
        const clarification = await syntheticResult(params);
        if (clarification) return clarification;
        const result = await doGenerate();
        return { ...cleanMetadata(result), content: await content(result.content, params) };
      },
      wrapStream: async ({ doStream, params }) => {
        const clarification = await syntheticResult(params);
        if (clarification) return { stream: new ReadableStream({ start(controller) {
          for (const chunk of [{ type: 'stream-start', warnings: [] }, { type: 'text-start', id: 'clarify' },
            { type: 'text-delta', id: 'clarify', delta: clarification.content[0].text },
            { type: 'text-end', id: 'clarify' },
            { type: 'finish', finishReason: clarification.finishReason, usage: clarification.usage }]) controller.enqueue(chunk);
          controller.close();
        } }) };
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
        authorizeTool(options.name, identity, options.policy ? { [options.name]: options.policy } : undefined);
        const signal = options.signal ?? execution?.abortSignal;
        const raw = serialize(input);
        if (await check(raw, { direction: 'output', identity, signal }) !== raw) {
          throw new PromptionError('TOOL_ARGUMENTS_REDACTED');
        }
        if (await check(raw, { direction: "input", identity, signal }) !== raw) {
          throw new PromptionError("TOOL_ARGUMENTS_REDACTED");
        }
        const retained = conversationEvidence(execution?.messages ?? [], options.securityMessages,
          { maxMessages: config.maxConversationMessages, maxChars: config.maxConversationChars });
        const current = options.originalText ?? retained.filter(message => message.role === 'user').at(-1)?.content;
        const messages = focusedToolEvidence(retained, identity, current);
        {
          const safe = await check(raw, { direction: "input", identity, signal,
            messages: [...messages, { role: "tool", content: raw, tool_name: options.name }] });
          if (safe !== raw) throw new PromptionError("TOOL_ARGUMENTS_REDACTED");
        }
        if (config.scopeEvaluator || missingReference(current ?? '', messages)) {
          const lastText = messages.filter(message => message.role === "user").at(-1)?.content;
          const texts = new Set([options.originalText ?? lastText, ...(lastText ? [lastText] : [])]);
          for (const text of texts) {
            await enforceScope(text, { identity, signal, systemPrompt: options.systemPrompt || 'Clarify missing context before any action.', messages,
              tool: { name: options.name, input: raw, description: definition.description },
              onScope: options.onScope });
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

  return Object.freeze({ check, checkScope, middleware, protectTool, protection });
}
