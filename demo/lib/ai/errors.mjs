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

export function aiFailure(error) {
  if (guardCodes.has(error?.code)) {
    const code = error.code;
    const status = error?.status === 403 ? 403 : 503;
    const reason = ['malicious_input', 'insufficient_scope', 'sensitive_output'].includes(error?.reason)
      ? error.reason : undefined;
    const scope = error?.scope && ['IN_SCOPE', 'OUT_OF_SCOPE', 'UNCERTAIN'].includes(error.scope.classification)
      && ['in_scope', 'topic_outside_scope', 'system_limit', 'ambiguous', 'scope_unavailable',
        'invalid_scope_response'].includes(error.scope.reason)
      ? { classification: error.scope.classification, reason: error.scope.reason,
        allowed: error.scope.classification === 'IN_SCOPE',
        status: [200, 403, 503].includes(error.scope.status) ? error.scope.status : status } : undefined;
    return { code, status, reason, scope };
  }

  if (operationalCodes.has(error?.code)) {
    const code = error.code;
    const status = error?.status || operationalCodes.get(code);
    return { code, status, reason: undefined, scope: undefined };
  }

  const rawStatus = error?.status || error?.statusCode;
  const status = [429, 499, 502, 503, 504].includes(rawStatus) ? rawStatus : 503;
  const code = status === 504 ? 'GATEWAY_TIMEOUT'
    : status === 429 ? 'QUOTA_EXCEEDED'
    : status === 502 ? 'INVALID_MODEL_RESPONSE'
    : status === 499 ? 'CANCELLED'
    : 'MODEL_UNAVAILABLE';
  return { code, status, reason: undefined, scope: undefined };
}
