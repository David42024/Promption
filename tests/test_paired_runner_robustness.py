"""Regression checks for billing ambiguity, persistence and experimental completion."""
import importlib.util
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('robust_bench', ROOT/'scripts/run_paired_2000_v9.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.mark.parametrize('code', [408, 500, 502, 503, 504])
def test_ambiguous_post_not_retried(code):
    args = SimpleNamespace(timeout=1, concurrency=1, requests_per_minute=0,
                           max_retries=4, retry_ambiguous=False, backoff=0, max_backoff=1)
    layer = bench.HttpLayer(args, ())
    layer.client.close()
    layer.client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(code, json={})))
    try:
        result = layer.call('POST', 'http://localhost/chat')
        assert len(result['attempts']) == 1
        assert result['http_attempts_latency_ms'] >= 0
        assert result['client_backoff_ms'] == 0
        assert result['latency_ms'] >= result['http_attempts_latency_ms']-.1
    finally:
        layer.close()


def test_corrupt_middle_event_rejected_and_incomplete_tail_recovered(tmp_path, monkeypatch):
    path = tmp_path/'events.jsonl'
    event = {'arm': 'protected', 'id': 'one', 'chat': {'data': {'execution_metrics': {'provider_calls': 0}}}}
    path.write_text(json.dumps(event)+'\nBROKEN\n'+json.dumps(event)+'\n')
    with pytest.raises(ValueError, match='Corrupt event'):
        bench.read_events(path)
    path.write_text(json.dumps(event)+'\n{"unfinished"')
    args = bench.args_parse(['--no-watchdog'])
    runner = bench.Runner(args, tmp_path, [])
    try:
        assert len(runner.events) == 1
        assert path.read_bytes().endswith(b'\n')
        assert list(tmp_path.glob('events-incomplete-*'))
    finally:
        runner.close()


def test_budget_stop_is_incomplete_without_chat(tmp_path, monkeypatch):
    args = bench.args_parse(['--no-watchdog', '--max-provider-calls', '1', '--provider-call-reservation', '2'])
    cases = bench.build_corpus(bench.read_seeds([ROOT/'data/validation/deployed_cases.jsonl']), 1, 1, 91)
    runner = bench.Runner(args, tmp_path, cases)
    monkeypatch.setattr(runner, 'preflight', lambda: None)
    monkeypatch.setattr(runner, 'set_arm', lambda arm: None)
    try:
        runner.run()
        status = json.loads((tmp_path/'execution-status.json').read_text())
        assert status['status'] == 'INCOMPLETE'
        assert status['pending'] == 4
        assert status['budget_stopped'] is True
        assert runner.provider_calls == 0
    finally:
        runner.close()


def test_watchdog_restores_after_real_parent_death(tmp_path, monkeypatch):
    state = {'filter_enabled': False, 'output_guard_enabled': False}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['filter_enabled' if body['action']=='filter' else 'output_guard_enabled'] = body['enabled']
            self.do_GET()
        def do_GET(self):
            content = json.dumps(state).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def log_message(self, *args):
            pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    output = tmp_path/'restoration.json'
    ready = tmp_path/'ready.json'
    watchdog = subprocess.Popen([sys.executable, str(ROOT/'scripts/paired_benchmark_watchdog.py'),
        '--parent', str(parent.pid), '--chat-url', f'http://127.0.0.1:{server.server_port}',
        '--output', str(output), '--ready', str(ready)])
    try:
        import time
        deadline = time.monotonic()+10
        while not ready.exists() and time.monotonic()<deadline:
            time.sleep(.05)
        assert ready.exists()
        parent.kill()
        parent.wait(timeout=5)
        assert watchdog.wait(timeout=20) == 0
        assert json.loads(output.read_text())['restored'] is True
        assert all(state.values())
    finally:
        for process in (parent, watchdog):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        server.shutdown()
        server.server_close()


def test_unknown_call_usage_stops_new_work(tmp_path, monkeypatch):
    args = bench.args_parse(['--no-watchdog'])
    cases = bench.build_corpus(bench.read_seeds([ROOT/'data/validation/deployed_cases.jsonl']), 1, 1, 91)
    runner = bench.Runner(args, tmp_path, cases)
    runner.write_event('protected', cases[0], {'http': 500, 'data': None}, {})
    try:
        runner.run_unit([cases[1]], 'protected')
        assert runner.unknown_calls == 1
        assert runner.budget_stopped
        assert len(runner.events) == 1
    finally:
        runner.close()


def test_changed_backend_model_rejected_on_resume(tmp_path, monkeypatch):
    args = bench.args_parse(['--no-watchdog'])
    runner = bench.Runner(args, tmp_path, [])
    model = ['model-one']
    def call(method, url, *args):
        if url.endswith('/health'):
            return {'http': 200, 'data': {'status': 'ok'}}
        if url.endswith('/status'):
            return {'http': 200, 'data': {'llm': {'default_model': model[0]}}}
        return {'http': 200, 'data': {'filter_enabled': True, 'output_guard_enabled': True}}
    monkeypatch.setattr(runner.http, 'call', call)
    try:
        runner.preflight()
        runner.preflight()
        model[0] = 'model-two'
        with pytest.raises(RuntimeError, match='fingerprint changed'):
            runner.preflight()
    finally:
        runner.close()


def test_ambiguous_retry_cannot_certify_total_tokens():
    row = {'case_kind': 'attack', 'technical_error': None, 'final_blocked': False,
           'known_total_tokens': 10, 'usage_complete': True, 'possible_duplicate_billing': True}
    assert bench.summarize_arm([row])['certified_token_total'] is None


def test_concurrent_reservation_prevents_second_chat(tmp_path, monkeypatch):
    args = bench.args_parse(['--no-watchdog', '--max-provider-calls', '2', '--provider-call-reservation', '2'])
    cases = bench.build_corpus(bench.read_seeds([ROOT/'data/validation/deployed_cases.jsonl']), 1, 1, 91)
    runner = bench.Runner(args, tmp_path, cases)
    entered = threading.Event()
    release = threading.Event()
    def call(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return {'http': 200, 'data': {'blocked': False, 'filter_enabled': True, 'output_guard_enabled': True,
                                    'execution_metrics': {'provider_calls': 2}}}
    monkeypatch.setattr(runner.http, 'call', call)
    worker = threading.Thread(target=runner.run_unit, args=([cases[0]], 'protected'))
    try:
        worker.start()
        assert entered.wait(5)
        runner.run_unit([cases[1]], 'protected')
        assert runner.budget_stopped
        assert runner.pending_calls == 2
        release.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert len(runner.events) == 1
        assert runner.pending_calls == 0
    finally:
        release.set()
        worker.join(timeout=5)
        runner.close()


def test_incomplete_cli_returns_nonzero(tmp_path, monkeypatch):
    original = bench.Runner
    class LimitedRunner(original):
        def preflight(self):
            pass
        def set_arm(self, arm):
            pass
    monkeypatch.setattr(bench, 'Runner', LimitedRunner)
    monkeypatch.setenv('VALIDATION_CHAT_TOKEN', 'synthetic-test-token')
    result = bench.main(['--execute', '--no-watchdog', '--benign', '1', '--attack', '1',
                         '--max-provider-calls', '1', '--provider-call-reservation', '2',
                         '--output', str(tmp_path/'experiment')])
    assert result == 2
    status = json.loads((tmp_path/'experiment/execution-status.json').read_text())
    assert status['pending'] == 4
