import { PromptionError } from "./errors.js";

function endpoint(value) {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new TypeError("A server HTTP(S) URL without credentials is required");
  }
  return url.toString().replace(/\/$/, "");
}

function riskScore(result, direction) {
  const scores = [result.input_risk_score, result.layers?.conversation?.input_risk_score, result.conversation?.input_risk_score];
  if (scores.some(score => score !== undefined && score !== null
      && (typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > 1))) {
    throw new PromptionError('INVALID_GUARD_RESPONSE', { status: 503, direction });
  }
  const present = scores.filter(score => typeof score === 'number');
  return present.length ? { inputRiskScore: Math.max(...present) } : {};
}

async function request(url, body, headers, config, signal) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason);
  if (signal?.aborted) throw signal.reason || new DOMException("Aborted", "AbortError");
  signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => controller.abort(), config.timeoutMs ?? 15000);
  try {
    const response = await (config.fetch ?? globalThis.fetch)(url, {
      method: "POST", headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body), signal: controller.signal, cache: "no-store",
      redirect: "error",
    });
    if (!response.ok) {
      let detail;
      try { detail = (await response.json())?.detail; } catch {}
      const code = response.status === 403 && detail?.code === "CONTENT_BLOCKED"
        ? "CONTENT_BLOCKED" : response.status === 503 && detail?.code === "GUARD_UNAVAILABLE"
          ? "GUARD_UNAVAILABLE" : "GUARD_REQUEST_FAILED";
      throw new PromptionError(code, {
        status: response.status === 403 ? 403 : 503,
        direction: ["input", "output"].includes(detail?.direction) ? detail.direction : undefined,
        reason: ["malicious_input", "insufficient_scope", "sensitive_output"].includes(detail?.reason)
          ? detail.reason : undefined,
      });
    }
    return await response.json();
  } catch (error) {
    if (signal?.aborted) throw signal.reason || error;
    if (error instanceof PromptionError) throw error;
    throw new PromptionError("GUARD_UNAVAILABLE", { status: 503, cause: error });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export function createFilterApiTransport(config) {
  const base = endpoint(config.baseUrl);
  if (!config.apiKey) throw new TypeError("Promption API key is required on the server");
  return async ({ text, direction, identity, signal, messages, context = {}, isolateHistory = false }) => {
    const result = await request(`${base}/api/v1/${direction === "input" ? "filter" : "output-guard"}`, {
      text, user_id: identity.userId, roles: identity.roles, context,
      ...(direction === "input" && messages?.length ? { messages } : {}),
      ...(direction === "input" ? { use_ml: config.useMl !== false } : {}),
      ...(direction === "input" && isolateHistory ? { isolate_history: true } : {}),
    }, { "X-Promption-API-Key": config.apiKey }, config, signal);
    if (config.tenantId && result.tenant_id !== config.tenantId) {
      throw new PromptionError("TENANT_MISMATCH", { status: 503, direction });
    }
    if (direction === "input") {
      if (['requires_scope_review', 'requires_output_guard'].some(key => result[key] !== undefined && typeof result[key] !== 'boolean')
          || ['requires_scope_review', 'requires_output_guard'].some(key => result.layers?.conversation?.[key] !== undefined
            && typeof result.layers.conversation[key] !== 'boolean')) {
        throw new PromptionError('INVALID_GUARD_RESPONSE', { status: 503, direction });
      }
      if (messages?.length && (result.layers?.conversation?.message_count !== messages.length
          || typeof result.layers?.conversation?.blocked !== "boolean")) {
        throw new PromptionError("CONVERSATION_NOT_CHECKED", { status: 503, direction });
      }
      if (typeof result.blocked !== "boolean" || !["ALLOWED", "GUARDED", "BLOCKED"].includes(result.decision)
          || (result.decision === "BLOCKED" && !result.blocked)) {
        throw new PromptionError("INVALID_GUARD_RESPONSE", { status: 503, direction });
      }
      return { allowed: !result.blocked && result.classification !== "MALICIOUS",
        ...riskScore(result, direction),
        control: 'injection', reason: result.blocked ? 'malicious_input' : undefined,
        text: typeof result.sanitized === "string" ? result.sanitized : text,
        action: result.decision, requiresOutputGuard: result.requires_output_guard === true || result.classification === 'UNCERTAIN',
        requiresScopeReview: result.requires_scope_review === true || result.layers?.conversation?.requires_scope_review === true,
        ...(result.assessments && Object.keys(result.assessments).length ? { assessments: result.assessments } : {}),
        ...(result.layers?.conversation ? { conversation: result.layers.conversation } : {}) };
    }
    if (!["PASS", "REDACT", "BLOCK"].includes(result.action)
        || (result.action === "REDACT" && typeof result.redacted_response !== "string")) {
      throw new PromptionError("INVALID_GUARD_RESPONSE", { status: 503, direction });
    }
    return { allowed: result.action !== "BLOCK", action: result.action,
      text: result.action === "REDACT" ? result.redacted_response : text };
  };
}

export function createGuardEndpointTransport(config) {
  const url = endpoint(config.url);
  if (!config.token) throw new TypeError("A server-to-server token is required");
  return async ({ text, direction, identity, signal, messages, isolateHistory = false }) => {
    const result = await request(url, {
      text, direction, user_id: identity.userId, roles: identity.roles,
      ...(direction === "input" && messages?.length ? { messages } : {}),
      ...(direction === "input" && isolateHistory ? { isolate_history: true } : {}),
    }, { "X-Chat-Service-Token": config.token }, config, signal);
    if (['requires_scope_review', 'requires_output_guard'].some(key => result[key] !== undefined && typeof result[key] !== 'boolean')) {
      throw new PromptionError('INVALID_GUARD_RESPONSE', { status: 503, direction });
    }
    if (direction === "input" && messages?.length && result.allowed
        && result.conversation_checked !== true && result.action !== "SKIPPED") {
      throw new PromptionError("CONVERSATION_NOT_CHECKED", { status: 503, direction });
    }
    return { ...result, ...riskScore(result, direction), requiresScopeReview: result.requires_scope_review === true,
      requiresOutputGuard: result.requires_output_guard === true };
  };
}
