"""Local-only tests for the full-chat research benchmark. No paid API calls."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from collections import Counter

import httpx
import pytest

HERE = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bench',HERE/'scripts/run_paired_2000_v9.py')
bench=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
SEEDS=HERE/'data/validation/deployed_cases.jsonl'


def test_exact_quotas_and_multiturn():
    cases=bench.build_corpus(bench.read_seeds([SEEDS]), 1000,1000,20261019)
    assert Counter(c['kind'] for c in cases)=={'benign':1000,'attack':1000}
    assert len({c['text'] for c in cases})==2000
    assert len({c['id'] for c in cases})==2000
    groups={}
    for case in cases:groups.setdefault(case['session_id'],[]).append(case)
    assert all([c['turn_index'] for c in u]==list(range(len(u))) for u in groups.values())
    assert any(set(c['kind'] for c in u)=={'benign','attack'} for u in groups.values())
    again=bench.build_corpus(bench.read_seeds([SEEDS]),1000,1000,20261019)
    assert cases==again


def test_different_seed_different_corpus():
    a=bench.build_corpus(bench.read_seeds([SEEDS]),20,20,10)
    b=bench.build_corpus(bench.read_seeds([SEEDS]),20,20,11)
    assert [c['text'] for c in a] != [c['text'] for c in b]


def test_known_attack_payload_preserved():
    seeds=bench.read_seeds([SEEDS]);selected=bench.build_corpus(seeds,20,20,5)
    mapping={c['id']:c['text'] for c in seeds}
    assert all(mapping[c['seed_id']] in c['text'] for c in selected)


def test_technical_failure_excluded_from_detection():
    assert bench.technical_reason({'blocked':True,'reason':'scope_truncated'},200)=='scope_truncated'
    assert bench.technical_reason({'blocked':True,'reason':'conversation_injection'},200) is None
    assert bench.technical_reason({'blocked':True},503)=='transport_or_invalid_response'
    assert bench.technical_reason({'blocked':False},200,arm_mismatch=True)=='arm_state_mismatch'


def test_rate_limit_retry(monkeypatch):
    args=SimpleNamespace(timeout=5,concurrency=1,requests_per_minute=0,max_retries=2,
                         retry_ambiguous=False,backoff=0,max_backoff=1)
    http=bench.HttpLayer(args,())
    calls=[]
    def mock(req):
        calls.append(req)
        return httpx.Response(429,headers={'Retry-After':'0'},json={'error':'slow'}) if len(calls)==1 else httpx.Response(200,json={'ok':True})
    http.client.close();http.client=httpx.Client(transport=httpx.MockTransport(mock))
    try:
        r=http.call('POST','http://localhost/api/v1/chat',{}, {'x':1})
        assert r['http']==200 and len(r['attempts'])==2
    finally:http.close()


def test_unrecoverable_errors_not_retried():
    args=SimpleNamespace(timeout=5,concurrency=1,requests_per_minute=0,max_retries=3,
                         retry_ambiguous=False,backoff=0,max_backoff=1)
    http=bench.HttpLayer(args,())
    calls=[]
    def mock(req):
        calls.append(1);return httpx.Response(403,json={'detail':'forbidden'})
    http.client.close();http.client=httpx.Client(transport=httpx.MockTransport(mock))
    try:
        r=http.call('POST','http://localhost/api/v1/chat',{}, {})
        assert r['http']==403 and len(calls)==1
    finally:http.close()


def test_end_to_end_fake_local_and_restore(monkeypatch,tmp_path):
    args=bench.args_parse(['--execute','--benign','4','--attack','4','--blocks','2',
        '--concurrency','2','--requests-per-minute','0','--output',str(tmp_path/'sim')])
    monkeypatch.setenv('VALIDATION_CHAT_TOKEN','synthetic_token_for_local_testing')
    corpus=bench.build_corpus(bench.read_seeds([SEEDS]),4,4,3)
    folder=tmp_path/'sim';folder.mkdir()
    state={'filter_enabled':True,'output_guard_enabled':True}
    all_requests=[]
    def mock(req):
        path=req.url.path
        if path.endswith('/status'):
            return httpx.Response(200,json={'version':'test','llm':{'default_model':'mock'}})
        if path.endswith('/health'):
            return httpx.Response(200,json={'status':'ok'})
        if path.endswith('/security/state'):
            if req.method=='POST':
                obj=json.loads(req.content)
                state['filter_enabled' if obj['action']=='filter' else 'output_guard_enabled']=obj['enabled']
            return httpx.Response(200,json=state)
        if path.endswith('/chat'):
            body=json.loads(req.content)
            all_requests.append((body,state.copy()))
            blocked=state['filter_enabled'] and 'ignora' in body['text'].lower()
            return httpx.Response(200,json={
                'blocked':blocked,'reply':'Respuesta de demostración' if not blocked else '',
                'reason':'conversation_injection' if blocked else None,
                'filter_enabled':state['filter_enabled'],
                'output_guard_enabled':state['output_guard_enabled'],
                'scope':{'classification':'IN_SCOPE'},'audit':[],
                'execution_metrics':{'provider_calls':1,'scope_calls':1,'generation_calls':0,
                 'total_tokens':10,'known_usage':{'total_tokens':10},
                 'usage_coverage':{'is_complete':True},'stages':{}}})
        raise AssertionError(path)
    runner=bench.Runner(args,folder,corpus)
    runner.http.client.close();runner.http.client=httpx.Client(transport=httpx.MockTransport(mock))
    try:runner.run()
    finally:runner.close()
    assert state=={'filter_enabled':True,'output_guard_enabled':True}
    assert len(all_requests)==16
    assert len(bench.read_events(folder/'events.jsonl'))==16
    assert (folder/'restored-security.json').exists()
    result=json.loads((folder/'summary.json').read_text())
    assert result['pairs_completed']==8
    assert result['protected']['cases']==8
    assert result['baseline']['cases']==8
    assert result['protected']['known_token_subtotal']==80
    assert result['baseline']['known_token_subtotal']==80
    import csv
    with (folder/'protected/full_chat_results.csv').open(encoding='utf-8-sig') as f:
        records=list(csv.DictReader(f))
    assert all(k in records[0] for k in bench.REQUIRED_COLUMNS)
    assert len(records)==8
    assert all(c['filter_enabled']=='True' for c in records)


def test_missing_usage_is_not_zeros():
    row={'case_kind':'attack','technical_error':None,'final_blocked':False,'usage_complete':False,
         'known_total_tokens':None, 'scope_decision':'IN_SCOPE','block_reason':None,
         'chat_client_latency_ms':30, 'family_id':'x'}
    result=bench.summarize_arm([row])
    assert result['certified_token_total'] is None
    assert result['usage_coverage_cases']['partial']==1


def test_canary_signal_without_disclosing_canary():
    from base64 import b64encode
    v='SYNTHETIC_CANARY_ABC12345'
    assert bench.canary_signal('token '+v,v)
    assert bench.canary_signal(b64encode(v.encode()).decode(),v)
    assert not bench.canary_signal('no secrets',v)
