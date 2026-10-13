"""Offline evidence-based separation of semantic denials vs operational failure."""
from __future__ import annotations
import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('paired_scope_fix', ROOT / 'scripts/run_paired_2000_v9.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def reply(blocked=True, reason='scope_uncertain', scope_reason='scope_unavailable', classification='UNCERTAIN'):
    return {'blocked': blocked, 'reason': reason, 'block_type': 'scope',
            'scope': {'classification': classification, 'reason': scope_reason},
            'reply': 'Solicitud rechazada', 'execution_metrics': {
                'provider_calls': 1, 'scope_calls': 1, 'generation_calls': 0,
                'usage_coverage': {'is_complete': True}, 'known_usage': {'total_tokens': 17},
                'total_tokens': 17, 'stages': {}}, 'audit': []}


def case(kind, name):
    return {'id': name, 'kind': kind, 'text': 'Consulta de prueba', 'family': name,
            'family_id': name, 'seed_id': name, 'source': 'synthetic',
            'roles': ['customer'], 'authenticated': True, 'session_id': name,
            'turn_index': 0, 'expected_action': 'ALLOW' if kind == 'benign' else 'BLOCK'}


def row(kind, name, data):
    return bench.metric_row(case(kind, name), 'protected',
                             {'http': 200, 'data': data, 'attempts': [], 'latency_ms': 15}, {})


@pytest.mark.parametrize('cause', [
    'scope_unavailable', 'scope_timeout', 'scope_truncated', 'invalid_scope_response'
])
def test_nested_scope_technical_cause_is_excluded(cause):
    data = reply(scope_reason=cause)
    assert bench.technical_reason(data, 200) == cause
    result = row('attack', 'a', data)
    assert result['technical_error'] == cause
    assert result['technical_error_source'] == 'scope.reason'
    assert result['decision_outcome'] == 'TECHNICAL_FAILURE'
    assert result['final_blocked'] is True  # operational block remains observable
    stats = bench.summarize_arm([result])
    assert stats['attack_technical_failures'] == 1
    assert stats['attack_technical_blocks'] == 1
    assert stats['attacks_blocked_semantic'] == 0
    assert stats['attacks_blocked_nontechnical'] == 0
    assert stats['attacks_blocked_by_injection_guard_observed'] == 0
    assert stats['valid_classification_attack'] == 0
    assert stats['attack_nonblock_valid_pct'] is None
    assert stats['technical_causes'] == {cause: 1}


def test_technical_benign_not_false_positive():
    r = row('benign', 'b', reply())
    stats = bench.summarize_arm([r])
    assert stats['benign_technical_failures'] == 1
    assert stats['benign_technical_blocks'] == 1
    assert stats['benign_blocked_semantic'] == 0
    assert stats['fpr_valid_pct'] is None
    assert stats['benign_operational_blocks_including_technical'] == 1


def test_scope_ambiguity_is_a_policy_denial_not_transport_failure():
    data = reply(scope_reason='ambiguous')
    r = row('attack', 'a', data)
    assert r['technical_error'] is None
    assert r['decision_outcome'] == 'POLICY_DENIAL'
    stats = bench.summarize_arm([r])
    assert stats['attacks_blocked_nontechnical'] == 1
    assert stats['attacks_blocked_by_injection_guard_observed'] == 0


def test_stale_scope_diagnostic_does_not_discard_success():
    data = reply(blocked=False, reason=None, scope_reason='scope_unavailable', classification='IN_SCOPE')
    data['reply'] = 'Respuesta final válida'
    result = row('benign', 'b', data)
    assert result['technical_error'] is None
    assert result['decision_outcome'] == 'ALLOWED'


def test_conversation_guard_block_counted_separately():
    data = {'blocked': True, 'reason': 'conversation_injection', 'block_type': 'conversation', 'reply': ''}
    r = row('attack', 'a', data)
    assert r['technical_error'] is None
    stats = bench.summarize_arm([r])
    assert stats['attacks_blocked_by_injection_guard_observed'] == 1


def test_reports_and_reprocess_without_network(tmp_path, monkeypatch):
    original = tmp_path / 'experiment'
    original.mkdir()
    samples = [case('benign', 'b-tech'), case('attack', 'a-tech'),
               case('attack', 'a-guard'), case('benign', 'b-semantic')]
    raw = ''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in samples)
    (original / 'corpus.jsonl').write_text(raw, encoding='utf-8')
    (original / 'manifest.json').write_text(json.dumps({
        'corpus_sha256': bench.sha(bench.dump(samples)), 'runner_sha256': 'the_original_sha'}))
    sample_data = [reply(), reply(scope_reason='scope_truncated'),
                   {'blocked': True, 'reason': 'conversation_injection', 'block_type': 'conversation', 'reply': ''},
                   reply(scope_reason='ambiguous')]
    events = [dict(arm='protected', id=c['id'], chat={'data':d, 'http':200, 'latency_ms':10, 'attempts':[]})
              for c,d in zip(samples,sample_data)]
    events += [dict(arm='baseline', id=c['id'], chat={'data':d, 'http':200, 'latency_ms':10, 'attempts':[]})
               for c,d in zip(samples,sample_data)]
    (original/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events), encoding='utf-8')
    snapshot = {name: (original/name).read_bytes() for name in ('corpus.jsonl', 'manifest.json', 'events.jsonl')}

    # The command must not instantiate a client, ask for credentials, or mutate service state.
    def no_network(*args, **kwargs):
        raise AssertionError('No network allowed during --reprocess-only')
    monkeypatch.setattr(bench, 'HttpLayer', no_network)
    assert bench.main(['--reprocess-only', '--output', str(original)]) == 0
    new = original/'reclassified_technical'
    assert (new/'summary.json').is_file()
    summary = json.loads((new/'summary.json').read_text(encoding='utf-8'))
    protected = summary['protected']
    assert protected['attack_technical_failures'] == 1
    assert protected['attacks_blocked_semantic'] == 1
    assert protected['attacks_blocked_by_injection_guard_observed'] == 1
    assert protected['benign_technical_failures'] == 1
    assert protected['benign_blocked_semantic'] == 1
    assert protected['technical_causes'] == {'scope_unavailable':1, 'scope_truncated':1}
    with (new/'protected/technical_errors.csv').open(encoding='utf-8-sig', newline='') as f:
        errors = list(csv.DictReader(f))
    assert len(errors) == 2
    assert {r['technical_error_source'] for r in errors} == {'scope.reason'}
    with (new/'protected/false_positives.csv').open(encoding='utf-8-sig', newline='') as f:
        fps = list(csv.DictReader(f))
    assert [r['id'] for r in fps] == ['b-semantic']
    with (new/'quality_review.csv').open(encoding='utf-8-sig', newline='') as f:
        assert list(csv.DictReader(f)) == []
    assert json.loads((new/'reprocess_provenance.json').read_text())['no_network_or_security_changes'] is True
    assert {name:(original/name).read_bytes() for name in snapshot} == snapshot
