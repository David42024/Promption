const guardCodes = new Set(['OUT_OF_SCOPE', 'SCOPE_UNCERTAIN', 'CONTENT_BLOCKED',
  'GUARD_UNAVAILABLE', 'INVALID_GUARD_RESPONSE', 'GUARD_REQUEST_FAILED', 'TOOL_ACCESS_DENIED',
  'CONVERSATION_TOO_LARGE', 'CONVERSATION_NOT_CHECKED', 'CONVERSATION_REDACTED',
  'UNTRUSTED_TOOL_CONTENT', 'TOOL_ARGUMENTS_REDACTED', 'STRUCTURED_OUTPUT_REDACTED',
  'UNINSPECTED_MODEL_FILE']);

export function aiFailure(error) {
  const code = guardCodes.has(error?.code) ? error.code : 'MODEL_UNAVAILABLE';
  const status = error?.status === 403 ? 403 : 503;
  const scope = error?.scope && ['IN_SCOPE', 'OUT_OF_SCOPE', 'UNCERTAIN'].includes(error.scope.classification)
    && ['in_scope', 'topic_outside_scope', 'system_limit', 'ambiguous', 'scope_unavailable',
      'invalid_scope_response'].includes(error.scope.reason)
    ? { classification: error.scope.classification, reason: error.scope.reason,
      allowed: error.scope.classification === 'IN_SCOPE',
      status: [200, 403, 503].includes(error.scope.status) ? error.scope.status : status } : undefined;
  return { code, status, scope };
}
