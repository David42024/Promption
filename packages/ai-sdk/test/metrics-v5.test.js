import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MetricsAggregator } from '../src/metrics.js';

test('zero is known but missing is not zero', () => {
  const agg = new MetricsAggregator();
  agg.addCall({ callType: 'scope', eventId:'0', promptTokens:0, completionTokens:0, totalTokens:0, reasoningTokens:0 });
  agg.addCall({ callType: 'generation', eventId:'missing', hasUsage:true });
  const result = agg.summary();
  assert.equal(result.provider_calls, 2);
  assert.equal(result.total_tokens, null);
  assert.equal(result.known_usage.total_tokens, 0);
  assert.equal(result.usage_coverage.calls_with_usage, 1);
  assert.equal(result.usage_coverage.calls_without_usage, 1);
  assert.equal(result.usage_coverage.is_complete, false);
});

test('invalid numeric usage does not inflate token totals', () => {
  const agg = new MetricsAggregator();
  agg.addCall({ eventId: 'bad', promptTokens: NaN, completionTokens: -5, totalTokens: Infinity });
  const result = agg.summary();
  assert.equal(result.total_tokens, null);
  assert.equal(result.usage_coverage.calls_without_usage, 1);
});
