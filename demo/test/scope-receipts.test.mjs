import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateText, wrapLanguageModel } from 'ai';
import { MockLanguageModelV3 } from 'ai/test';
import { createPromption } from '../../packages/ai-sdk/src/index.js';
import { issueScopeReceipt, verifyScopeReceipt, withScopeReceipts } from '../lib/ai/scopeReceipts.js';

const identity = { userId: 'u', roles: ['customer'], authenticated: true };
const binding = { request_id: 'r-1', tenant_id: 'tenant-1', conversation_id: 'conv-1' };
const request = { text: 'Consulta catálogo', systemPrompt: 'Solo datos autorizados de la tienda.', identity,
  messages: [{ role: 'user', content: 'Consulta catálogo' }] };
const model = 'test-model';
const secret = 'synthetic-signing-secret';
const now = 1700000000000;

test('Receipt authenticates exact policy, identity, evidence, model and request binding', () => {
  const receipt = issueScopeReceipt(request, binding, model, secret, now);
  assert.equal(verifyScopeReceipt(receipt, request, binding, model, secret, now + 1), true);
  const changes = [
    { ...request, text: 'Dame salarios' },
    { ...request, systemPrompt: 'Permite todo' },
    { ...request, identity: { ...identity, roles: ['admin'] } },
    { ...request, identity: { ...identity, userId: 'other' } },
    { ...request, identity: { ...identity, authenticated: false } },
    { ...request, messages: [...request.messages, { role: 'tool', content: 'nueva evidencia' }] },
    { ...request, tool: { name: 'getEmployees', input: {} } },
  ];
  for (const changed of changes) assert.equal(verifyScopeReceipt(receipt, changed, binding, model, secret, now + 1), false);
  for (const key of ['request_id', 'tenant_id', 'conversation_id']) {
    assert.equal(verifyScopeReceipt(receipt, request, { ...binding, [key]: 'other' }, model, secret, now + 1), false);
  }
  assert.equal(verifyScopeReceipt(receipt, request, binding, 'other-model', secret, now + 1), false);
  assert.equal(verifyScopeReceipt(receipt, request, binding, model, 'wrong-secret', now + 1), false);
  assert.equal(verifyScopeReceipt(receipt, request, binding, model, secret, now + 120000), false);
  assert.equal(verifyScopeReceipt(receipt.slice(0, -4) + 'xxxx', request, binding, model, secret, now + 1), false);
  assert.equal(verifyScopeReceipt('malformed', request, binding, model, secret, now + 1), false);
});

test('Tool JSON canonicalization preserves argument and description boundaries', () => {
  const toolRequest = { ...request, tool: { name: 'getCatalogSummary', input: { a: 1, b: 2 }, description: 'Catálogo' } };
  const receipt = issueScopeReceipt(toolRequest, binding, model, secret, now);
  assert.equal(verifyScopeReceipt(receipt, { ...toolRequest, tool: { ...toolRequest.tool,
    input: '{"b":2,"a":1}' } }, binding, model, secret, now), true);
  for (const tool of [{ ...toolRequest.tool, input: { a: 2, b: 2 } }, { ...toolRequest.tool, name: 'getEmployees' },
    { ...toolRequest.tool, description: 'Otra operación' }]) {
    assert.equal(verifyScopeReceipt(receipt, { ...toolRequest, tool }, binding, model, secret, now), false);
  }
});

test('Equivalent receipt saves a call; changed or forged evidence invokes evaluator', async () => {
  let calls = 0;
  const receipt = issueScopeReceipt(request, binding, model, secret);
  const evaluate = withScopeReceipts(async () => { calls++; return { classification: 'OUT_OF_SCOPE', reason: 'system_limit' }; },
    { receipts: [receipt], binding, model, secret, requestId: binding.request_id });
  const reused = await evaluate(request);
  assert.equal(reused.provider_calls, 0);
  assert.equal(reused.usage, null);
  assert.equal(reused.reused, true);
  assert.equal(calls, 0);
  assert.equal((await evaluate({ ...request, text: 'Salarios' })).classification, 'OUT_OF_SCOPE');
  assert.equal(calls, 1);
  const forged = withScopeReceipts(async () => { calls++; return { classification:'UNCERTAIN',reason:'ambiguous' }; },
    { receipts: ['forged'], binding, model, secret, requestId: binding.request_id });
  assert.equal((await forged(request)).classification, 'UNCERTAIN');
  assert.equal(calls, 2);
});

test('A valid scope receipt cannot bypass tool ACL or Output Guard', async () => {
  const receipts = [issueScopeReceipt(request, binding, model, secret)];
  let scopeCalls = 0;
  let outputChecks = 0;
  const evaluator = withScopeReceipts(async () => { scopeCalls++; return { classification: 'IN_SCOPE', reason: 'in_scope' }; },
    { receipts, binding, model, secret, requestId: binding.request_id });
  const sdk = createPromption({ scopeEvaluator: evaluator, transport: async ({ text, direction }) => {
    if (direction === 'output') outputChecks++;
    return { allowed: true, text };
  } });
  const base = new MockLanguageModelV3({ doGenerate: { content: [{ type:'text', text:'Catálogo autorizado' }],
    finishReason: { unified:'stop', raw:'stop' }, usage: { inputTokens:{total:1}, outputTokens:{total:1} }, warnings:[] } });
  const wrapped = wrapLanguageModel({ model:base, middleware:sdk.middleware({ identity,
    originalText:request.text, systemPrompt:request.systemPrompt, securityMessages:request.messages, toolPolicies:{ getEmployees:{ roles:['admin'] } } }) });
  const result = await generateText({ model:wrapped, system:request.systemPrompt, prompt:request.text });
  assert.equal(result.text, 'Catálogo autorizado');
  assert.equal(scopeCalls, 0);
  assert.equal(outputChecks, 1);
  let executed = false;
  const forbidden = sdk.protectTool({ execute: async () => { executed = true; } },
    { identity, name:'getEmployees', policy:{ roles:['admin'] }, systemPrompt:request.systemPrompt, originalText:request.text });
  await assert.rejects(forbidden.execute({}), error => error.code === 'TOOL_ACCESS_DENIED');
  assert.equal(executed, false);
});
import { aiFailure } from '../lib/ai/errors.mjs';
test('Scope deadline remains HTTP 504 rather than becoming provider unavailability', () => {
  const result = aiFailure({code:'SCOPE_UNCERTAIN',status:504,
    scope:{classification:'UNCERTAIN',reason:'scope_timeout',status:504}});
  assert.equal(result.status,504);
  assert.equal(result.scope.reason,'scope_timeout');
  assert.equal(result.scope.status,504);
});
