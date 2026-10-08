const guardCodes = new Set(['OUT_OF_SCOPE', 'SCOPE_UNCERTAIN', 'CONTENT_BLOCKED',
  'GUARD_UNAVAILABLE', 'INVALID_GUARD_RESPONSE', 'GUARD_REQUEST_FAILED', 'TOOL_ACCESS_DENIED',
  'CONVERSATION_TOO_LARGE', 'CONVERSATION_NOT_CHECKED', 'CONVERSATION_REDACTED',
  'UNTRUSTED_TOOL_CONTENT', 'TOOL_ARGUMENTS_REDACTED', 'STRUCTURED_OUTPUT_REDACTED',
  'UNINSPECTED_MODEL_FILE']);

const operationalCodes = new Map([
  ['GATEWAY_TIMEOUT', 504],
  ['QUOTA_EXCEEDED', 429],
  ['INVALID_MODEL_RESPONSE', 502],
  ['CONFIGURATION_ERROR', 503],
  ['MODEL_UNAVAILABLE', 503],
  ['MODEL_EMPTY_RESPONSE', 502],
  ['CANCELLED', 499]
]);

function resolveTargetError(error) {
  if (guardCodes.has(error?.code) || operationalCodes.has(error?.code)) {
    return error;
  }
  let curr = error?.cause;
  const seen = new Set([error]);
  let depth = 0;
  while (curr && depth < 5 && !seen.has(curr)) {
    seen.add(curr);
    depth++;
    if (guardCodes.has(curr?.code) || operationalCodes.has(curr?.code)) {
      return curr;
    }
    curr = curr.cause;
  }
  return error;
}

export function aiFailure(error, options = {}) {
  const signal = options?.signal;
  const isExplicitAbort = options?.aborted ?? signal?.aborted;

  const target = resolveTargetError(error);

  if (guardCodes.has(target?.code)) {
    const code = target.code;
    const status = target?.status === 403 ? 403 : (target?.status === 503 ? 503 : (code === 'CONTENT_BLOCKED' || code === 'OUT_OF_SCOPE' || code === 'TOOL_ACCESS_DENIED' ? 403 : 503));
    const reason = ['malicious_input', 'insufficient_scope', 'sensitive_output'].includes(target?.reason)
      ? target.reason : undefined;
    const scope = target?.scope && ['IN_SCOPE', 'OUT_OF_SCOPE', 'UNCERTAIN'].includes(target.scope.classification)
      && ['in_scope', 'topic_outside_scope', 'system_limit', 'ambiguous', 'scope_unavailable',
        'invalid_scope_response'].includes(target.scope.reason)
      ? { classification: target.scope.classification, reason: target.scope.reason,
        allowed: target.scope.classification === 'IN_SCOPE',
        status: [200, 403, 503].includes(target.scope.status) ? target.scope.status : status } : undefined;
    return { code, status, reason, scope };
  }

  if (operationalCodes.has(target?.code)) {
    const code = target.code;
    const status = target?.status || operationalCodes.get(code);
    return { code, status, reason: undefined, scope: undefined };
  }

  const isTimeout = target?.name === 'TimeoutError'
    || error?.name === 'TimeoutError'
    || String(target?.message || '').toLowerCase().includes('timeout')
    || String(error?.message || '').toLowerCase().includes('timeout')
    || (target?.name === 'AbortError' && String(target?.message || '').toLowerCase().includes('time'));

  if (isTimeout) {
    return { code: 'GATEWAY_TIMEOUT', status: 504, reason: undefined, scope: undefined };
  }

  const hasAbort = target?.name === 'AbortError' || error?.name === 'AbortError';
  if (hasAbort) {
    if (isExplicitAbort === false) {
      return { code: 'MODEL_UNAVAILABLE', status: 503, reason: undefined, scope: undefined };
    }
    return { code: 'CANCELLED', status: 499, reason: undefined, scope: undefined };
  }

  const rawStatus = target?.status || target?.statusCode || error?.status || error?.statusCode;
  const status = [429, 499, 502, 503, 504].includes(rawStatus) ? rawStatus : 503;
  const code = status === 504 ? 'GATEWAY_TIMEOUT'
    : status === 429 ? 'QUOTA_EXCEEDED'
    : status === 502 ? 'INVALID_MODEL_RESPONSE'
    : status === 499 ? 'CANCELLED'
    : 'MODEL_UNAVAILABLE';
  return { code, status, reason: undefined, scope: undefined };
}
