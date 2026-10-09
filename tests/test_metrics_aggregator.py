"""Unit tests for the metrics consumption contract and aggregator (Task 1)."""
import pytest
from promption.metrics_aggregator import MetricsAggregator, UsageEvent


def test_two_complete_usages_are_summed():
    agg = MetricsAggregator()
    agg.add_call(
        call_type="generation",
        calls=1,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        reasoning_tokens=2,
        event_id="gen-1",
    )
    agg.add_call(
        call_type="scope",
        calls=1,
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
        reasoning_tokens=3,
        event_id="scope-1",
    )
    res = agg.summary()
    assert res["provider_calls"] == 2
    assert res["generation_calls"] == 1
    assert res["scope_calls"] == 1
    assert res["prompt_tokens"] == 30
    assert res["completion_tokens"] == 15
    assert res["total_tokens"] == 45
    assert res["reasoning_tokens"] == 5
    assert res["known_usage"]["prompt_tokens"] == 30
    assert res["known_usage"]["completion_tokens"] == 15
    assert res["known_usage"]["total_tokens"] == 45
    assert res["known_usage"]["reasoning_tokens"] == 5
    assert res["usage_coverage"]["calls_total"] == 2
    assert res["usage_coverage"]["calls_with_usage"] == 2
    assert res["usage_coverage"]["calls_without_usage"] == 0
    assert res["usage_coverage"]["is_complete"] is True
    assert res["usage_coverage"]["fields"]["prompt_tokens"] is True
    assert res["usage_coverage"]["fields"]["completion_tokens"] is True
    assert res["usage_coverage"]["fields"]["total_tokens"] is True
    assert res["usage_coverage"]["fields"]["reasoning_tokens"] is True


def test_explicit_zero_remains_zero():
    agg = MetricsAggregator()
    agg.add_call(
        call_type="generation",
        calls=1,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        reasoning_tokens=0,
        event_id="zero-1",
    )
    res = agg.summary()
    assert res["provider_calls"] == 1
    assert res["prompt_tokens"] == 0
    assert res["completion_tokens"] == 0
    assert res["total_tokens"] == 0
    assert res["reasoning_tokens"] == 0
    assert res["known_usage"]["prompt_tokens"] == 0
    assert res["known_usage"]["completion_tokens"] == 0
    assert res["known_usage"]["total_tokens"] == 0
    assert res["known_usage"]["reasoning_tokens"] == 0
    assert res["usage_coverage"]["is_complete"] is True
    assert res["usage_coverage"]["fields"]["total_tokens"] is True


def test_known_and_unknown_call_leaves_full_total_null_and_preserves_subtotal():
    agg = MetricsAggregator()
    agg.add_call(
        call_type="generation",
        calls=1,
        prompt_tokens=15,
        completion_tokens=15,
        total_tokens=30,
        reasoning_tokens=None,
        event_id="gen-1",
    )
    # Scope initiated but usage unknown (None)
    agg.add_call(
        call_type="scope",
        calls=1,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        reasoning_tokens=None,
        has_usage=False,
        event_id="scope-1",
    )
    res = agg.summary()
    assert res["provider_calls"] == 2
    assert res["generation_calls"] == 1
    assert res["scope_calls"] == 1
    # Full totals must be None (unknown)
    assert res["prompt_tokens"] is None
    assert res["completion_tokens"] is None
    assert res["total_tokens"] is None
    assert res["reasoning_tokens"] is None
    # Known usage must preserve the known subtotal
    assert res["known_usage"]["prompt_tokens"] == 15
    assert res["known_usage"]["completion_tokens"] == 15
    assert res["known_usage"]["total_tokens"] == 30
    assert res["known_usage"]["reasoning_tokens"] is None
    # Coverage must indicate incompleteness
    assert res["usage_coverage"]["calls_total"] == 2
    assert res["usage_coverage"]["calls_with_usage"] == 1
    assert res["usage_coverage"]["calls_without_usage"] == 1
    assert res["usage_coverage"]["is_complete"] is False
    assert res["usage_coverage"]["fields"]["total_tokens"] is False


def test_unknown_reasoning_does_not_invalidate_known_total_tokens():
    agg = MetricsAggregator()
    agg.add_call(
        call_type="generation",
        calls=1,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        reasoning_tokens=None,  # unknown reasoning
        event_id="gen-1",
    )
    res = agg.summary()
    assert res["provider_calls"] == 1
    assert res["prompt_tokens"] == 10
    assert res["completion_tokens"] == 20
    assert res["total_tokens"] == 30  # total is known!
    assert res["reasoning_tokens"] is None  # reasoning is unknown
    assert res["known_usage"]["total_tokens"] == 30
    assert res["known_usage"]["reasoning_tokens"] is None
    assert res["usage_coverage"]["fields"]["total_tokens"] is True
    assert res["usage_coverage"]["fields"]["reasoning_tokens"] is False
    assert res["usage_coverage"]["is_complete"] is False  # not complete for all fields because reasoning missing


def test_omitted_operation_does_not_invalidate_totals():
    agg = MetricsAggregator()
    # No scope calls made (omitted)
    agg.add_call(
        call_type="generation",
        calls=1,
        prompt_tokens=15,
        completion_tokens=15,
        total_tokens=30,
        reasoning_tokens=0,
        event_id="gen-1",
    )
    res = agg.summary()
    assert res["provider_calls"] == 1
    assert res["scope_calls"] == 0
    assert res["total_tokens"] == 30
    assert res["usage_coverage"]["calls_total"] == 1
    assert res["usage_coverage"]["calls_with_usage"] == 1
    assert res["usage_coverage"]["calls_without_usage"] == 0
    assert res["usage_coverage"]["is_complete"] is True


def test_duplicate_events_not_counted_twice():
    agg = MetricsAggregator()
    added1 = agg.add_call(
        call_type="scope",
        calls=1,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        event_id="evt-dup-1",
    )
    added2 = agg.add_call(
        call_type="scope",
        calls=1,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        event_id="evt-dup-1",
    )
    assert added1 is True
    assert added2 is False
    res = agg.summary()
    assert res["provider_calls"] == 1
    assert res["scope_calls"] == 1
    assert res["total_tokens"] == 15


def test_reasoning_tokens_not_added_again_to_total():
    agg = MetricsAggregator()
    agg.add_call(
        call_type="generation",
        calls=1,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        reasoning_tokens=5,
        event_id="gen-1",
    )
    res = agg.summary()
    assert res["total_tokens"] == 30  # NOT 35!
    assert res["reasoning_tokens"] == 5


def test_concurrent_requests_do_not_share_state():
    agg1 = MetricsAggregator()
    agg2 = MetricsAggregator()
    agg1.add_call(call_type="generation", calls=1, total_tokens=10, event_id="e1")
    agg2.add_call(call_type="generation", calls=1, total_tokens=20, event_id="e2")
    assert agg1.summary()["total_tokens"] == 10
    assert agg2.summary()["total_tokens"] == 20
