import { test } from 'node:test';
import assert from 'node:assert/strict';
import { aiFailure } from '../lib/ai/errors.mjs';

test('bridge errors preserve security codes without exposing provider messages', () => {
  const result = aiFailure({ code: 'OUT_OF_SCOPE', status: 403, message: 'private prompt',
    scope: { classification: 'OUT_OF_SCOPE', reason: 'system_limit', allowed: true, status: 403 } });
  assert.deepEqual(result, { code: 'OUT_OF_SCOPE', status: 403,
    scope: { classification: 'OUT_OF_SCOPE', reason: 'system_limit', allowed: false, status: 403 } });
  assert.ok(!JSON.stringify(result).includes('private prompt'));
});

test('unknown error codes and scope details are not returned to chat clients', () => {
  const result = aiFailure({ code: 'private provider detail', message: 'credential',
    scope: { classification: 'UNCERTAIN', reason: 'private system content', status: 'credential' } });
  assert.deepEqual(result, { code: 'MODEL_UNAVAILABLE', status: 503, scope: undefined });
});
