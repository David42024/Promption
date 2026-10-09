import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MetricsAggregator } from '../src/metrics.js';

test('two complete usages are summed', () => {
  const agg = new MetricsAggregator();
  agg.addCall({
    callType: 'generation',
    calls: 1,
    promptTokens: 10,
    completionTokens: 5,
    totalTokens: 15,
    reasoningTokens: 2,
    eventId: 'gen-1',
  });
  agg.addCall({
    callType: 'scope',
    calls: 1,
    promptTokens: 20,
    completionTokens: 10,
    totalTokens: 30,
    reasoningTokens: 3,
    eventId: 'scope-1',
  });
  const res = agg.summary();
  assert.equal(res.provider_calls, 2);
  assert.equal(res.generation_calls, 1);
  assert.equal(res.scope_calls, 1);
  assert.equal(res.prompt_tokens, 30);
  assert.equal(res.completion_tokens, 15);
  assert.equal(res.total_tokens, 45);
  assert.equal(res.reasoning_tokens, 5);
  assert.equal(res.known_usage.total_tokens, 45);
  assert.equal(res.usage_coverage.is_complete, true);
  assert.equal(res.usage_coverage.calls_total, 2);
  assert.equal(res.usage_coverage.calls_with_usage, 2);
  assert.equal(res.usage_coverage.calls_without_usage, 0);
});

test('explicit zero remains zero', () => {
  const agg = new MetricsAggregator();
  agg.addCall({
    callType: 'generation',
    calls: 1,
    promptTokens: 0,
    completionTokens: 0,
    totalTokens: 0,
    reasoningTokens: 0,
    eventId: 'zero-1',
  });
  const res = agg.summary();
  assert.equal(res.provider_calls, 1);
  assert.equal(res.prompt_tokens, 0);
  assert.equal(res.completion_tokens, 0);
  assert.equal(res.total_tokens, 0);
  assert.equal(res.reasoning_tokens, 0);
  assert.equal(res.known_usage.total_tokens, 0);
  assert.equal(res.usage_coverage.is_complete, true);
});

test('one known and one unknown call leaves full total null and preserves subtotal', () => {
  const agg = new MetricsAggregator();
  agg.addCall({
    callType: 'generation',
    calls: 1,
    promptTokens: 15,
    completionTokens: 15,
    totalTokens: 30,
    eventId: 'gen-1',
  });
  agg.addCall({
    callType: 'scope',
    calls: 1,
    hasUsage: false,
    eventId: 'scope-1',
  });
  const res = agg.summary();
  assert.equal(res.provider_calls, 2);
  assert.equal(res.generation_calls, 1);
  assert.equal(res.scope_calls, 1);
  assert.equal(res.prompt_tokens, null);
  assert.equal(res.completion_tokens, null);
  assert.equal(res.total_tokens, null);
  assert.equal(res.known_usage.total_tokens, 30);
  assert.equal(res.usage_coverage.is_complete, false);
  assert.equal(res.usage_coverage.calls_total, 2);
  assert.equal(res.usage_coverage.calls_with_usage, 1);
  assert.equal(res.usage_coverage.calls_without_usage, 1);
});

test('unknown reasoning does not invalidate total_tokens if it was reported', () => {
  const agg = new MetricsAggregator();
  agg.addCall({
    callType: 'generation',
    calls: 1,
    promptTokens: 10,
    completionTokens: 20,
    totalTokens: 30,
    reasoningTokens: null,
    eventId: 'gen-1',
  });
  const res = agg.summary();
  assert.equal(res.provider_calls, 1);
  assert.equal(res.total_tokens, 30);
  assert.equal(res.reasoning_tokens, null);
  assert.equal(res.known_usage.total_tokens, 30);
  assert.equal(res.usage_coverage.fields.total_tokens, true);
  assert.equal(res.usage_coverage.fields.reasoning_tokens, false);
});

test('omitted operation does not invalidate totals', () => {
  const agg = new MetricsAggregator();
  agg.addCall({
    callType: 'generation',
    calls: 1,
    promptTokens: 15,
    completionTokens: 15,
    totalTokens: 30,
    reasoningTokens: 0,
    eventId: 'gen-1',
  });
  const res = agg.summary();
  assert.equal(res.provider_calls, 1);
  assert.equal(res.scope_calls, 0);
  assert.equal(res.total_tokens, 30);
  assert.equal(res.usage_coverage.is_complete, true);
});

test('duplicate events not counted twice', () => {
  const agg = new MetricsAggregator();
  const added1 = agg.addCall({ callType: 'scope', calls: 1, totalTokens: 15, eventId: 'dup-1' });
  const added2 = agg.addCall({ callType: 'scope', calls: 1, totalTokens: 15, eventId: 'dup-1' });
  assert.equal(added1, true);
  assert.equal(added2, false);
  assert.equal(agg.summary().provider_calls, 1);
  assert.equal(agg.summary().total_tokens, 15);
});

test('reasoning tokens not added again to total', () => {
  const agg = new MetricsAggregator();
  agg.addCall({
    callType: 'generation',
    calls: 1,
    promptTokens: 10,
    completionTokens: 20,
    totalTokens: 30,
    reasoningTokens: 5,
    eventId: 'gen-1',
  });
  assert.equal(agg.summary().total_tokens, 30);
  assert.equal(agg.summary().reasoning_tokens, 5);
});

test('concurrent requests do not share state', () => {
  const agg1 = new MetricsAggregator();
  const agg2 = new MetricsAggregator();
  agg1.addCall({ callType: 'generation', calls: 1, totalTokens: 10, eventId: 'e1' });
  agg2.addCall({ callType: 'generation', calls: 1, totalTokens: 20, eventId: 'e2' });
  assert.equal(agg1.summary().total_tokens, 10);
  assert.equal(agg2.summary().total_tokens, 20);
});
