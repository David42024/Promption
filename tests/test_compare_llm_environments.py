"""Offline tests for paired scenario orchestration."""
import json
from scripts import compare_llm_environments as runner


def test_percentiles_and_empty_samples():
    assert runner.percentile([], .95) is None
    assert runner.percentile([10, 20, 30], .5) == 20
    assert runner.percentile([10, 20, 30], .95) == 29


def test_dry_run_never_opens_backend(monkeypatch):
    monkeypatch.setattr(runner, 'execute_scenario', lambda *a: (_ for _ in ()).throw(AssertionError('network forbidden')))
    assert runner.main(['--dry-run', '--limit', '5']) == 0


def test_generation_latency_excludes_blocked_requests():
    records = [{'chat': {'http': 200, 'latency_ms': 10, 'data': {'execution_metrics': {'generation_calls': 0}}}},
               {'chat': {'http': 200, 'latency_ms': 100, 'data': {'execution_metrics': {'generation_calls': 1}}}},
               {'chat': {'http': 503, 'latency_ms': 200, 'data': {}}}]
    result = runner.timing(records)
    assert result['all_http_success']['n'] == 2
    assert result['with_generation']['p50_ms'] == 100


def test_paired_runs_alternate_and_preserve_case_selection(monkeypatch, tmp_path):
    calls = []
    def fake(name, args, cases, output, repeat):
        calls.append((name, repeat, [c['id'] for c in cases]))
        return [{'id': c['id'], 'provider_calls': 0, 'known_total_tokens': None} for c in cases], {'scenario': name, 'repeat': repeat}
    monkeypatch.setattr(runner, 'execute_scenario', fake)
    flags = ['--execute', '--limit', '5', '--repeats', '2', '--output-dir', str(tmp_path)]
    for name in ('local', 'incubunt'):
        for suffix in ('VALIDATION_CHAT_TOKEN', 'VALIDATION_FILTER_KEY'):
            monkeypatch.setenv(name.upper() + '_' + suffix, 'fake-only-test')
        for service in ('chat', 'filter', 'demo'):
            flags += [f'--{name}-{service}-url', 'http://localhost:9999']
    assert runner.main(flags) == 0
    assert [(x[0], x[1]) for x in calls] == [('local', 1), ('incubunt', 1), ('incubunt', 2), ('local', 2)]
    assert all(x[2] == calls[0][2] for x in calls)
    folder = next(tmp_path.iterdir())
    assert len(json.loads((folder / 'summary.json').read_text())) == 4
    assert (folder / 'comparison-2.csv').exists()
