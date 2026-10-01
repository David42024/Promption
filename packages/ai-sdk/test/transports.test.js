import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createGuardEndpointTransport } from '../src/transports.js';

const identity = { userId: 'guest', roles: ['guest'], authenticated: false };
for (const [status, detail, expected] of [
  [403, { code: 'CONTENT_BLOCKED', direction: 'output', reason: 'insufficient_scope' }, 'CONTENT_BLOCKED'],
  [503, { code: 'GUARD_UNAVAILABLE', direction: 'input' }, 'GUARD_UNAVAILABLE'],
  [403, { code: 'arbitrary secret', direction: 'arbitrary secret' }, 'GUARD_REQUEST_FAILED'],
  [500, { code: 'CONTENT_BLOCKED', direction: 'output' }, 'GUARD_REQUEST_FAILED'],
  [403, 'arbitrary secret', 'GUARD_REQUEST_FAILED'],
]) {
  test(`guard HTTP ${status} preserves only recognized security metadata (${expected})`, async () => {
    const transport = createGuardEndpointTransport({ url: 'http://localhost/guard', token: 'test-only',
      fetch: async () => Response.json({ detail }, { status }) });
    await assert.rejects(transport({ text: 'capabilities', direction: 'output', identity }), error => {
      assert.equal(error.code, expected);
      assert.equal(error.status, status === 403 ? 403 : 503);
      assert.equal(error.direction, ['input', 'output'].includes(detail.direction) ? detail.direction : undefined);
      assert.equal(error.reason, detail.reason === 'insufficient_scope' ? 'insufficient_scope' : undefined);
      assert.ok(!error.message.includes('arbitrary secret'));
      return true;
    });
  });
}
