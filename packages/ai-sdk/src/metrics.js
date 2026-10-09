/**
 * Shared consumption contract and metrics aggregator for @promption/ai-sdk and the Next.js bridge.
 */
export class MetricsAggregator {
  constructor() {
    this._events = new Map();
    this._seenIds = new Set();
    this.generationCalls = 0;
    this.scopeCalls = 0;
    this.failedCalls = 0;
  }

  addCall({
    callType = "generation",
    calls = 1,
    promptTokens = null,
    completionTokens = null,
    totalTokens = null,
    reasoningTokens = null,
    hasUsage = null,
    failed = false,
    eventId = null,
    metadata = {},
  } = {}) {
    if (eventId) {
      if (this._seenIds.has(eventId)) return false;
      this._seenIds.add(eventId);
    } else {
      eventId = `${callType}-${this._events.size + 1}`;
    }

    const p = typeof promptTokens === "number" ? promptTokens : null;
    const c = typeof completionTokens === "number" ? completionTokens : null;
    const t = typeof totalTokens === "number" ? totalTokens : null;
    const r = typeof reasoningTokens === "number" ? reasoningTokens : null;

    const actualHasUsage = hasUsage !== null && hasUsage !== undefined
      ? Boolean(hasUsage)
      : (p !== null || c !== null || t !== null || r !== null);

    const callsCnt = Number.isFinite(calls) ? Math.max(0, Math.floor(calls)) : 0;
    if (callType === "scope") this.scopeCalls += callsCnt;
    else if (callType === "generation") this.generationCalls += callsCnt;
    if (failed) this.failedCalls += callsCnt;

    this._events.set(eventId, {
      eventId,
      callType,
      providerCalls: callsCnt,
      promptTokens: p,
      completionTokens: c,
      totalTokens: t,
      reasoningTokens: r,
      hasUsage: actualHasUsage,
      metadata,
    });
    return true;
  }

  summary() {
    const totalProviderCalls = this.generationCalls + this.scopeCalls;

    let knownP = null;
    let knownC = null;
    let knownT = null;
    let knownR = null;

    const fieldsComplete = {
      prompt_tokens: true,
      completion_tokens: true,
      total_tokens: true,
      reasoning_tokens: true,
    };

    let callsWithUsage = 0;
    let callsWithoutUsage = 0;

    for (const evt of this._events.values()) {
      if (evt.providerCalls <= 0) continue;

      if (evt.hasUsage) {
        callsWithUsage += evt.providerCalls;
      } else {
        callsWithoutUsage += evt.providerCalls;
      }

      if (evt.promptTokens !== null) {
        knownP = (knownP ?? 0) + evt.promptTokens;
      } else {
        fieldsComplete.prompt_tokens = false;
      }

      if (evt.completionTokens !== null) {
        knownC = (knownC ?? 0) + evt.completionTokens;
      } else {
        fieldsComplete.completion_tokens = false;
      }

      if (evt.totalTokens !== null) {
        knownT = (knownT ?? 0) + evt.totalTokens;
      } else if (evt.promptTokens !== null && evt.completionTokens !== null) {
        knownT = (knownT ?? 0) + (evt.promptTokens + evt.completionTokens);
      } else {
        fieldsComplete.total_tokens = false;
      }

      if (evt.reasoningTokens !== null) {
        knownR = (knownR ?? 0) + evt.reasoningTokens;
      } else {
        fieldsComplete.reasoning_tokens = false;
      }
    }

    if (totalProviderCalls === 0) {
      return {
        provider_calls: 0,
        generation_calls: 0,
        scope_calls: 0,
        failed_calls: this.failedCalls,
        prompt_tokens: null,
        completion_tokens: null,
        total_tokens: null,
        reasoning_tokens: null,
        known_usage: {
          prompt_tokens: null,
          completion_tokens: null,
          total_tokens: null,
          reasoning_tokens: null,
        },
        usage_coverage: {
          calls_total: 0,
          calls_with_usage: 0,
          calls_without_usage: 0,
          is_complete: true,
          fields: {
            prompt_tokens: true,
            completion_tokens: true,
            total_tokens: true,
            reasoning_tokens: true,
          },
        },
      };
    }

    const isComplete = Object.values(fieldsComplete).every(Boolean);
    const fullP = fieldsComplete.prompt_tokens ? knownP : null;
    const fullC = fieldsComplete.completion_tokens ? knownC : null;
    const fullT = fieldsComplete.total_tokens ? knownT : null;
    const fullR = fieldsComplete.reasoning_tokens ? knownR : null;

    return {
      provider_calls: totalProviderCalls,
      generation_calls: this.generationCalls,
      scope_calls: this.scopeCalls,
      failed_calls: this.failedCalls,
      prompt_tokens: fullP,
      completion_tokens: fullC,
      total_tokens: fullT,
      reasoning_tokens: fullR,
      known_usage: {
        prompt_tokens: knownP,
        completion_tokens: knownC,
        total_tokens: knownT,
        reasoning_tokens: knownR,
      },
      usage_coverage: {
        calls_total: totalProviderCalls,
        calls_with_usage: callsWithUsage,
        calls_without_usage: callsWithoutUsage,
        is_complete: isComplete,
        fields: fieldsComplete,
      },
    };
  }
}
