import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createTrackingModel } from '../lib/ai/tracking.js';
import { providerUsage } from '../lib/ai/providerUsage.js';
import { aiFailure } from '../lib/ai/errors.mjs';
import { createPromption, PromptionError, MetricsAggregator } from '@promption/ai-sdk';

test('policy diagnosis survives wrapped SDK failures without private text', () => {
  const error = new PromptionError('CONTENT_BLOCKED', { direction: 'output', reason: 'insufficient_scope', policyId: 'internal.stock' });
  const result = aiFailure(new Error('wrapper', { cause: error }));
  assert.equal(result.direction, 'output');
  assert.equal(result.policyId, 'internal.stock');
  assert.equal(aiFailure(new PromptionError('CONTENT_BLOCKED', { policyId: 'https://secret.test/key=SECRET' })).policyId, undefined);
});

test('provider usage is observed before a later output denial', async () => {
  const totals = new MetricsAggregator();
  const raw = { inputTokens: { total: 10 }, outputTokens: { total: 3, reasoning: 1 } };
  const tracked = createTrackingModel({ doStream: async () => ({ stream: new ReadableStream({ start(c) {
    c.enqueue({ type: 'text-delta', delta: 'private' });
    c.enqueue({ type: 'finish', usage: raw });
    c.close();
  } }) }) }, () => {}, usage => totals.addCall({ ...providerUsage(usage), eventId: 'generation' }));
  const result = await tracked.doStream({});
  for await (const chunk of result.stream) {}
  const promption = createPromption({ transport: async () => ({ allowed: false, reason: 'insufficient_scope', policy_id: 'internal.stock' }) });
  await assert.rejects(promption.check('Stock: 125', { direction: 'output', identity: { userId: 'u', roles: ['customer'] } }), error => error.policyId === 'internal.stock');
  assert.equal(totals.summary().provider_calls, 1);
  assert.equal(totals.summary().total_tokens, 13);
});

test('missing token fields remain unknown', () => {
  assert.equal(providerUsage({ inputTokens: { total: 10 } }).totalTokens, null);
  assert.equal(providerUsage({ inputTokens: 0, outputTokens: 0 }).totalTokens, 0);
});
