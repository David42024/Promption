import { test } from 'node:test';
import assert from 'node:assert/strict';
import { aiFailure } from '../lib/ai/errors.mjs';

test('bridge errors preserve security codes without exposing provider messages', () => {
  const result = aiFailure({ code: 'OUT_OF_SCOPE', status: 403, message: 'private prompt',
    scope: { classification: 'OUT_OF_SCOPE', reason: 'system_limit', allowed: true, status: 403 } });
  assert.deepEqual(result, { code: 'OUT_OF_SCOPE', status: 403, reason: undefined,
    scope: { classification: 'OUT_OF_SCOPE', reason: 'system_limit', allowed: false, status: 403 } });
  assert.ok(!JSON.stringify(result).includes('private prompt'));
});

test('unknown error codes and scope details are not returned to chat clients', () => {
  const result = aiFailure({ code: 'private provider detail', message: 'credential',
    scope: { classification: 'UNCERTAIN', reason: 'private system content', status: 'credential' } });
  assert.deepEqual(result, { code: 'MODEL_UNAVAILABLE', status: 503, reason: undefined, scope: undefined });
});

test('operational errors map to typed codes and correct HTTP status without raw body', () => {
  assert.deepEqual(aiFailure({ code: 'GATEWAY_TIMEOUT', status: 504, message: 'internal secret url' }),
    { code: 'GATEWAY_TIMEOUT', status: 504, reason: undefined, scope: undefined });

  assert.deepEqual(aiFailure({ code: 'QUOTA_EXCEEDED', status: 429 }),
    { code: 'QUOTA_EXCEEDED', status: 429, reason: undefined, scope: undefined });

  assert.deepEqual(aiFailure({ code: 'INVALID_MODEL_RESPONSE', status: 502 }),
    { code: 'INVALID_MODEL_RESPONSE', status: 502, reason: undefined, scope: undefined });

  assert.deepEqual(aiFailure({ code: 'CONFIGURATION_ERROR', status: 503 }),
    { code: 'CONFIGURATION_ERROR', status: 503, reason: undefined, scope: undefined });

  assert.deepEqual(aiFailure({ statusCode: 504, message: 'raw body text' }),
    { code: 'GATEWAY_TIMEOUT', status: 504, reason: undefined, scope: undefined });

  assert.deepEqual(aiFailure({ statusCode: 429 }),
    { code: 'QUOTA_EXCEEDED', status: 429, reason: undefined, scope: undefined });

  assert.deepEqual(aiFailure({ statusCode: 499 }),
    { code: 'CANCELLED', status: 499, reason: undefined, scope: undefined });
});
