import test from 'node:test';
import assert from 'node:assert/strict';
import { createGuardEndpointTransport, createPromption } from '../src/index.js';

test('HTTP policy denial preserves direction and policy without retry', async () => {
  let calls = 0;
  const transport = createGuardEndpointTransport({ url: 'https://guard.test', token: 'test-token', fetch: async () => {
    calls++;
    return new Response(JSON.stringify({ detail: { code: 'CONTENT_BLOCKED', direction: 'output', reason: 'insufficient_scope', policy_id: 'internal.stock' } }), { status: 403 });
  } });
  await assert.rejects(createPromption({ transport }).check('Stock: 125', { direction: 'output', identity: { userId: 'u', roles: ['customer'] } }),
    error => error.direction === 'output' && error.reason === 'insufficient_scope' && error.policyId === 'internal.stock');
  assert.equal(calls, 1);
});
