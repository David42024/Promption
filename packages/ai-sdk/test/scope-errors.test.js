import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPromption } from '../src/index.js';

for (const [reason, status] of [['ambiguous',403], ['scope_timeout',504], ['scope_unavailable',503],
  ['scope_truncated',403], ['invalid_scope_response',503]]) {
  test(`Scope preserves failure cause ${reason} and observed usage`, async () => {
    const sdk = createPromption({ transport:async ({text}) => ({allowed:true,text}), scopeEvaluator:async () => ({
      classification:'UNCERTAIN', reason, provider_calls:1, usage:{ prompt_tokens:0,completion_tokens:null,total_tokens:null } }) });
    const decision = await sdk.checkScope('Consulta catálogo', { systemPrompt:'Solo tienda', identity:{userId:'u',roles:['customer'],authenticated:true} });
    assert.equal(decision.reason, reason);
    assert.equal(decision.status, status);
    assert.equal(decision.provider_calls, 1);
    assert.equal(decision.allowed, false);
    assert.equal(decision.usage.prompt_tokens, 0);
    assert.equal(decision.usage.total_tokens, null);
  });
}

test('Scope distinguishes internal timeout from external cancellation', async () => {
  const sdk = createPromption({ transport:async ({text}) => ({allowed:true,text}), scopeEvaluator:async () => {
    throw new DOMException('synthetic timeout','TimeoutError');
  } });
  const options = { systemPrompt:'Solo tienda', identity:{userId:'u',roles:['customer'],authenticated:true} };
  const decision = await sdk.checkScope('Catálogo', options);
  assert.equal(decision.reason,'scope_timeout');
  assert.equal(decision.status,504);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(sdk.checkScope('Catálogo', { ...options, signal:controller.signal }), error => error.name === 'AbortError');
});
