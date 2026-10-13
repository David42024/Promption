from types import SimpleNamespace

import httpx
import pytest

from scripts import run_real_paired_benchmark as bench


def test_corpus_distribution_and_reproducibility():
    rows = bench.corpus(bench.ROOT / 'data/validation/deployed_cases.jsonl')
    assert len(rows) == 5000
    assert len({r['text'] for r in rows}) == 5000
    assert bench.Counter(r['kind'] for r in rows) == {'benign': 2500, 'attack': 2000, 'policy': 500}
    assert rows == bench.corpus(bench.ROOT / 'data/validation/deployed_cases.jsonl')
    assert len({r['family_id'] for r in rows}) == 45


def test_filter_block_does_not_generate():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={'blocked': True})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = bench.protected(client, {'id': 'x', 'text': 'x', 'roles': [], 'messages': []},
            SimpleNamespace(filter_url='https://filter.test', model='configured', max_tokens=512), 'secret', 'filter-secret')
    assert len(calls) == 1
    assert result['provider_calls'] == 0
    assert result['valid'] and not result['leaked']
    assert result['usage']['total_tokens'] == 0


@pytest.mark.parametrize('payload', [[], {'choices': [None]}, {'choices': [{'message': {}, 'finish_reason': 'stop'}]}])
def test_invalid_provider_payload_is_not_success(payload):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as client:
        result = bench.generate(client, {'text': 'hi', 'messages': []}, 'configured', 'secret', 512)
    assert result['provider_calls'] == 1
    assert not result['valid']
    assert result['leaked'] is None


def test_guard_redacts_actual_generated_canary():
    def handler(request):
        if request.url.path.endswith('/filter'):
            return httpx.Response(200, json={'blocked': False})
        if request.url.host == 'api.openai.com':
            return httpx.Response(200, json={'choices': [{'message': {'content': bench.CANARY}, 'finish_reason': 'stop'}]})
        return httpx.Response(200, json={'action': 'REDACT', 'redacted_response': '[REDACTED]'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = bench.protected(client, {'id': 'x', 'text': 'x', 'roles': [], 'messages': []},
            SimpleNamespace(filter_url='https://filter.test', model='configured', max_tokens=512), 'secret', 'filter-secret')
    assert result['generation_leaked'] is True
    assert result['valid'] and result['leaked'] is False
    assert result['usage'] is None


def test_errors_excluded_and_skipped_layers_not_negatives():
    records = [{'case': {'kind': 'attack', 'family_id': 'a'},
                'baseline': {'valid': False, 'provider_calls': 1, 'leaked': None},
                'protected': {'valid': True, 'provider_calls': 0, 'leaked': False, 'blocked': True,
                    'filter': {'data': {'blocked': True, 'layers': {'ml': {'blocked': None}}}},
                    'usage': {'total_tokens': 0}}}]
    summary = bench.summarize(records)
    assert summary['asr_baseline_comparable'] is None
    assert summary['comparable_attacks'] == 0
    assert summary['modes']['baseline']['total_tokens'] is None
    assert summary['modes']['protected']['total_tokens'] == 0
    assert summary['classification_matrices']['ml']['unevaluated'] == 1


def test_dry_run_exports_corpus_without_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    output = tmp_path / 'corpus.jsonl'
    assert bench.main(['--model', 'configured', '--dry-run', '--write-corpus', str(output)]) == 0
    assert len(output.read_text(encoding='utf-8').splitlines()) == 5000


def test_resume_does_not_repeat_saved_calls(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-secret')
    monkeypatch.setenv('VALIDATION_FILTER_KEY', 'filter-test-secret')
    calls = []
    def handler(request):
        if request.url.host == 'api.openai.com':
            calls.append(request)
            return httpx.Response(200, json={'choices': [{'message': {'content': 'Hola'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 4, 'completion_tokens': 1, 'total_tokens': 5}})
        return httpx.Response(200, json={'blocked': False, 'action': 'PASS'})
    original = httpx.Client
    monkeypatch.setattr(bench.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    common = ['--model', 'configured', '--filter-url', 'https://filter.test', '--execute', '--benign', '1', '--attack', '0', '--policy', '0', '--delay', '0']
    folder = tmp_path / 'results'
    assert bench.main(common + ['--output', str(folder)]) == 0
    assert len(calls) == 2
    assert bench.main(common + ['--resume', str(folder)]) == 0
    assert len(calls) == 2
    assert 'test-secret' not in (folder / 'arms.jsonl').read_text()
