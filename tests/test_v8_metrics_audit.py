"""V8 ledger and audit invariants; no network calls."""
from promption.metrics_aggregator import MetricsAggregator
from scripts.audit_v8_offline import summarize


def test_partial_usage_remains_null_with_sanitized_call_ledger():
    m = MetricsAggregator()
    m.add_call('scope', calls=1, prompt_tokens=5, completion_tokens=0,
               total_tokens=5, reasoning_tokens=0, event_id='scope-1')
    m.add_call('generation', calls=1, prompt_tokens=None, completion_tokens=None,
               total_tokens=None, reasoning_tokens=None, event_id='gen-2')
    result = m.summary()
    assert result['total_tokens'] is None
    assert result['known_usage']['total_tokens'] == 5
    ledger = m.diagnostic_ledger()
    assert len(ledger['events']) == 2
    assert ledger['events'][1]['known_fields']['total_tokens'] is False
    assert 'prompt' not in str(ledger).lower().replace('prompt_tokens','')


def test_duplicate_calls_not_double_counted_and_remote_limited():
    m = MetricsAggregator()
    assert m.add_call('scope', calls=1, event_id='same')
    assert not m.add_call('scope', calls=1, event_id='same')
    assert m.summary()['scope_calls'] == 1
    assert m.diagnostic_ledger(limit=0)['truncated']


def test_audit_does_not_count_technical_error_as_semantic_detection():
    rows = [
        dict(arm='protected',id='a-v6-1-0',kind='attack',blocked='true',reason='conversation_injection',
             usage_complete='true',known_total_tokens='10'),
        dict(arm='protected',id='a-v6-2-0',kind='attack',blocked='true',reason='scope_truncated',
             usage_complete='false',known_total_tokens='5'),
    ]
    result = summarize(rows)['arm_summaries']['protected']
    assert result['blocked_by_kind']['attack'] == 2
    assert result['technical_failures'] == 1
    assert result['certified_total_tokens'] is None
    assert result['known_tokens_lower_bound'] == 15
