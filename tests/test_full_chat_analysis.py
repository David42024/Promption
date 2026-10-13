from collections import Counter
from pathlib import Path

import pytest

from scripts.full_chat_analysis import diagnostics, sample_sessions, stage_summary
from scripts.run_deployed_validation import load_and_validate_cases
ROOT = Path(__file__).resolve().parents[1]


def test_sampling_is_exact_reproducible_and_preserves_sessions():
    seeds = load_and_validate_cases(ROOT / 'data/validation/deployed_cases.jsonl')
    cases = sample_sessions(seeds, 5000, 42)
    assert len(cases) == len({c['id'] for c in cases}) == 5000
    assert cases == sample_sessions(seeds, 5000, 42)
    assert cases != sample_sessions(seeds, 5000, 43)
    original = Counter(c['conversation_group'] for c in seeds if c['conversation_group'])
    actual = Counter(c['conversation_group'] for c in cases if c['conversation_group'])
    for group, count in actual.items():
        assert count == original[group.rsplit('-rep-', 1)[0]]


def test_weights_select_only_requested_kind():
    seeds = load_and_validate_cases(ROOT / 'data/validation/deployed_cases.jsonl')
    cases = sample_sessions(seeds, 30, weights=(100, 0, 0))
    assert all(c['kind'] == 'benign' for c in cases)


def test_invalid_sampling():
    with pytest.raises(ValueError):
        sample_sessions([], 0)
    with pytest.raises(ValueError):
        sample_sessions([], 10, weights=(0, 0, 0))


def test_unreported_and_skipped_not_invented():
    row = diagnostics({'case': {'id': 'x'}, 'chat': {'data': {'execution_metrics': {
        'stages': {'scope': {'status': 'skipped', 'latency_ms': None}}}}}})
    assert row['scope_stage_status'] == 'skipped'
    assert row['scope_expected_match'] is None
    assert row['tools_allowed_count'] is None
    summary = stage_summary([row])
    assert summary['scope']['statuses'] == {'skipped': 1}
    assert summary['scope']['latency_ms']['95'] is None
    assert summary['mcp_audit']['cases_with_audit'] == 0
    assert summary['tools']['statuses'] == {'unreported': 1}


def test_scope_and_tools_have_separate_ground_truth():
    row = diagnostics({'case': {'id': 'x', 'expected_scope': 'IN_SCOPE', 'expected_tools': ['catalog']},
                       'chat': {'data': {'scope': {'classification': 'IN_SCOPE'},
                           'audit': [{'tool': 'catalog', 'allowed': True}, {'tool': 'private', 'allowed': False}]}}})
    assert row['scope_expected_match'] is True
    assert row['expected_tools_match'] is True
    assert row['tools_denied_count'] == 1
