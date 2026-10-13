"""Execution-only addendum for the user's $5, pinned-snapshot, 20-pair gate."""
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.synthetic_v9_research import ROOT, OUT, read, dump, sha, verify
from scripts import scientific_evaluation as science
from scripts import run_paired_2000_v9 as paired
from scripts.run_final_scientific_v9 import ScientificRunner

MODEL='gpt-5-nano-2025-08-07'
FOLDER=OUT/'e2_results/prepared'
LEDGER=OUT/'e2_results/authorized-openai-ledger.json'

def gateway_type():
    """Reuse the original gateway, changing model configuration and settled sum only."""
    path=ROOT/'scripts/experimental_openai_budget_gateway.py'
    source=path.read_text(encoding='utf-8').replace('"gpt-5-nano"',repr(MODEL))
    source=source.replace('Decimal(a["reserved_usd"])','Decimal(a.get("conservative_usd", a["reserved_usd"]))')
    namespace={'__name__':'authorized_gateway','__file__':str(path)}
    exec(compile(source,str(path),'exec'),namespace)
    Base=namespace['BudgetGateway']
    class Gateway(Base):
        def _state(self):
            state=super()._state()
            for item in state['attempts']:
                amount=Decimal(item.get('conservative_usd',item['reserved_usd']))
                if not Decimal(0)<=amount<=self.upper_charge(): raise ValueError('Invalid conservative ledger amount')
            return state
        def _finish(self,attempt,fields):
            usage=fields.get('provider_usage') or {}
            inp=usage.get('input_tokens',usage.get('prompt_tokens'))
            out=usage.get('output_tokens',usage.get('completion_tokens'))
            known=type(inp) is int and type(out) is int and 0<=inp<=400000 and 0<=out<=6144
            fields['conservative_usd']=str((Decimal(inp)*Decimal('.05')+Decimal(out)*Decimal('.40'))/Decimal(1000000)) if known else str(self.upper_charge())
            fields['usage_known_for_cost']=known
            fields['halt_after_attempt']=not known or fields.get('provider_model')!=MODEL or fields.get('state')!='PROVIDER_RESPONDED'
            super()._finish(attempt,fields)
        def forward(self,path,body,authorization):
            with self.lock:
                if any(a.get('halt_after_attempt') or a['state']=='RESERVED_BEFORE_DISPATCH' for a in self._state()['attempts']):
                    raise namespace['BudgetRejected']('Unreconciled provider dispatch or model mismatch; no further charges')
            return super().forward(path,body,authorization)
    return Gateway,namespace['serve']

def select_pilot(rows):
    selected=[]
    for family,n in [('catalog',2),('commercial',2),('inventory',2),('authorized_admin',1),('quoted',1),('direct',2),('role',1),('restricted',2),('commercial_manipulation',1),('obfuscated',1)]:
        selected.extend([r for r in rows if r['family_id']==family][:n])
    for family in ['multi','attack_multi']:
        unit=next(r['session_id'] for r in rows if r['family_id']==family)
        selected.extend(r for r in rows if r['session_id']==unit)
    assert len(selected)==20 and sum(r['kind']=='attack' for r in selected)==10
    units=list(dict.fromkeys(r['session_id'] for r in selected))
    ordered=[r for unit in units for r in rows if r['session_id']==unit]+[r for r in rows if r['session_id'] not in units]
    return selected,ordered

class StagedRunner(ScientificRunner):
    def __init__(self,args,folder,rows,pilot,gateway):
        super().__init__(args,folder,rows)
        self.runtime['model']=MODEL; self.runtime['tool_model']=MODEL
        self.pilot={r['id'] for r in pilot}; self.gateway=gateway; self.checked=False
        self.reconciliation=None
        path=OUT/'e2_results/POST_RECONCILIATION.json'
        if path.exists():
            self.reconciliation=json.loads(path.read_text(encoding='utf-8'))
            key=tuple(self.reconciliation['event_key'])
            event=self.events.get(key)
            if not event or event['chat']['http']!=503 or self.reconciliation['status']!='RECONCILED': raise RuntimeError('Reconciliation does not bind the original failed request')
            self.unknown_calls-=1; self.provider_calls+=self.reconciliation['external_provider_attempts']
    def run_unit(self,unit,arm):
        if list(self.folder.glob('intent-*.json')): raise RuntimeError('Unreconciled Chat POST intent; no replay')
        before=self.gateway.snapshot()
        if Decimal(before['reserved_usd'])+self.gateway.upper_charge()>Decimal('5') or before['attempts']>=1200:
            self.budget_stopped=True; return
        super().run_unit(unit,arm)
        if any(a.get('halt_after_attempt') for a in self.gateway._state()['attempts']):
            raise RuntimeError('Unknown provider consumption or effective model mismatch; stopped')
        if self.unknown_calls: raise RuntimeError('Unknown backend provider-call counter; stopped')
    def set_arm(self,arm):
        done={id for id in self.pilot if ('protected',id) in self.events and ('baseline',id) in self.events}
        if done==self.pilot and not self.checked:
            self.restore(); self.active_arm=None
            if self.get_state()['filter_enabled'] is not True or self.get_state()['output_guard_enabled'] is not True: raise RuntimeError('Pilot restoration failed')
            observed=0
            for id in sorted(self.pilot):
                a,b=self.events[('protected',id)]['chat'],self.events[('baseline',id)]['chat']
                if a.get('effective_identity_sha256')!=b.get('effective_identity_sha256') or a.get('functional_history_sha256')!=b.get('functional_history_sha256'): raise RuntimeError('Pair identity/history mismatch')
                for arm2,event in [('protected',a),('baseline',b)]:
                    data=event.get('data') or {}; expected=arm2=='protected'
                    reconciled=self.reconciliation and [arm2,id]==self.reconciliation['event_key']
                    if not reconciled and (event.get('http')!=200 or data.get('filter_enabled') is not expected or data.get('output_guard_enabled') is not expected): raise RuntimeError('Pilot HTTP/arm evidence invalid')
                    calls=(data.get('execution_metrics') or {}).get('provider_calls')
                    if reconciled: calls=self.reconciliation['external_provider_attempts']
                    if type(calls) is not int: raise RuntimeError('Pilot call instrumentation unknown')
                    observed+=calls
            budget=self.gateway.snapshot()
            if observed!=budget['attempts']: raise RuntimeError('Backend/gateway attempt counts differ at pilot gate')
            if list(self.folder.glob('intent-*.json')): raise RuntimeError('Unreconciled pilot intent')
            from scripts.synthetic_v9_oracles import adjudicate
            cases={r['id']:r for r in self.corpus}
            outcomes=[adjudicate(cases[id],self.events[(arm2,id)]) for id in sorted(self.pilot) for arm2 in ['protected','baseline']]
            dump(OUT/'e2_results/pilot_gate.json',{'status':'PASS','pairs':20,'traversals':40,'provider_attempts_backend_plus_external_reconciliation':observed,'gateway':budget,'restoration_verified':True,'identity_history_match':True,'reconciled_technical_failure':self.reconciliation,'oracles':outcomes})
            self.checked=True
            print('PILOT GATE PASS: 20 pairs / 40 traversals; continuing frozen 200 pairs',flush=True)
        super().set_arm(arm)

def main():
    import httpx
    import psutil
    from dotenv import dotenv_values
    verify(); manifest=science.verify_freeze(FOLDER)
    if list(FOLDER.glob('intent-*.json')): raise ValueError('Unreconciled POST intent exists; no automatic replay')
    resuming=(FOLDER/'events.jsonl').exists() and bool(read(FOLDER/'events.jsonl'))
    if resuming:
        reconciliation=json.loads((OUT/'e2_results/POST_RECONCILIATION.json').read_text(encoding='utf-8'))
        if reconciliation['original_event_sha256']!=sha((FOLDER/'events.jsonl').read_bytes()): raise ValueError('Reconciliation hash mismatch; no replay')
    rows=read(FOLDER/'corpus.jsonl'); pilot,ordered=select_pilot(rows)
    binding={'approved_by':'USER','user_message_reference':'2026-10-13: explicit E2 authorization USD 5, 1200 attempts, 20-pair initial gate, pinned snapshot',
             'max_usd':5,'max_provider_attempts':1200,'model':MODEL,'corpus_hash_manifest_sha256':sha((OUT/'datasets/corpus_hashes.json').read_bytes()),
             'pilot_ids':[r['id'] for r in pilot],'pilot_selected_before_dispatch':True,'oracle_sha256':sha((ROOT/'scripts/synthetic_v9_oracles.py').read_bytes()),
             'code_sha256':sha(Path(__file__).read_bytes()),'production_or_corpus_changes':False,'runtime_override_only':'authorized snapshot and incremental budget; original preparation remains immutable'}
    binding['execution_transport']='VERCEL_AI_URL=http://127.0.0.1:3100/api/ai/turn; scope remains /api/ai/scope via existing urljoin'
    binding['resume_without_repeating_failed_traversal']=bool(resuming)
    dump(OUT/'e2_results'/('EXECUTION_RESUME_ADDENDUM.json' if resuming else 'USER_AUTHORIZATION_AND_EXECUTION_ADDENDUM.json'),binding)
    env=os.environ.copy()
    for path in [ROOT/'.env',ROOT/'chat-service/.env',ROOT/'demo/.env.local']:
        if path.exists(): env.update({k:v for k,v in dotenv_values(path).items() if v})
    if not env.get('OPENAI_API_KEY'): raise ValueError('OpenAI key unavailable')
    token=secrets.token_hex(32); key=secrets.token_hex(32); work=OUT/'e2_runtime'
    env.update(CHAT_SERVICE_TOKEN=token,VALIDATION_CHAT_TOKEN=token,VALIDATION_FILTER_KEY=key,PROMPTION_API_KEYS='tenant123.unitru:'+key,
               PROMPTION_ADMIN_API_KEYS='',PIF_API_KEYS='',PIF_LLM_API_KEY='',PROMPTION_API_KEY=key,PROMPTION_TENANT_ID='tenant123.unitru',PROMPTION_DEMO_MODE='false',
               FILTER_API_URL='http://127.0.0.1:8100',FILTER_API_KEY=key,TENANT_ID='tenant123.unitru',CHAT_API_URL='http://127.0.0.1:8101',
               NEXT_PUBLIC_CHAT_API_URL='http://127.0.0.1:8101',OPENAI_MODEL=MODEL,OPENAI_TOOL_MODEL=MODEL,OPENAI_REASONING_EFFORT='minimal',
               OPENAI_BASE_URL='http://127.0.0.1:3199/v1',VERCEL_AI_URL='http://127.0.0.1:3100/api/ai/turn',STORAGE_BACKEND='sqlite',PROMPTION_STORAGE_BACKEND='sqlite',
               SQLITE_DB_PATH=manifest['configured_runtime']['sqlite_db_path'],SECURITY_STATE_PATH=str(work/'security-state.json'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
               LLM_PROVIDER_ORDER='openai',LLM_PROVIDER_TIMEOUT_SECONDS='90',LLM_TOTAL_TIMEOUT_SECONDS='120',LLM_MAX_ATTEMPTS='1',DEBUG='false',PYTHONPATH=str(ROOT))
    for k in ['VALIDATION_CHAT_TOKEN','VALIDATION_FILTER_KEY','OPENAI_API_KEY']: os.environ[k]=env[k]
    with httpx.Client(timeout=1,trust_env=False) as client:
        for port in [3199,8100,8101,3100]:
            try:
                client.get(f'http://127.0.0.1:{port}/'); raise ValueError('Dedicated port occupied')
            except httpx.HTTPError: pass
    Gateway,serve=gateway_type(); gateway=Gateway(LEDGER,env['OPENAI_API_KEY'],max_calls=1200,max_usd='5')
    original_post=gateway.client.post
    traces=OUT/'e2_results/provider_originals'; traces.mkdir(exist_ok=True)
    def traced_post(url,**kwargs):
        number=len(gateway._state()['attempts'])
        (traces/f'{number:04d}-request.json').write_bytes(kwargs['content'])
        response=original_post(url,**kwargs)
        (traces/f'{number:04d}-response.bin').write_bytes(response.content)
        dump(traces/f'{number:04d}-receipt.json',{'http':response.status_code,'request_id':response.headers.get('x-request-id'),'content_type':response.headers.get('content-type'),'request_sha256':sha(kwargs['content']),'response_sha256':sha(response.content)})
        return response
    gateway.client.post=traced_post
    threading.Thread(target=serve,args=(gateway,3199),daemon=True).start()
    py=str(ROOT/'.venv-review/Scripts/python.exe'); node='C:/Users/USERJSSV/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    specs=[('filter',[py,'-m','uvicorn','promption.api.main:app','--host','127.0.0.1','--port','8100'],ROOT),
           ('chat',[py,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8101'],ROOT/'chat-service'),
           ('bridge',[node,str(ROOT/'demo/node_modules/next/dist/bin/next'),'dev','-p','3100'],ROOT/'demo')]
    processes=[]; streams=[]; runner=None; failure=None
    try:
        for name,command,cwd in specs:
            stream=(work/(name+'-authorized.log')).open('a',encoding='utf-8'); streams.append(stream)
            processes.append(subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW))
        with httpx.Client(timeout=30,trust_env=False) as client:
            for url,expected in [('http://127.0.0.1:3199/budget',200),('http://127.0.0.1:8100/api/v1/health',200),('http://127.0.0.1:8101/api/v1/status',200),('http://127.0.0.1:3100/api/ai/turn',405)]:
                for _ in range(60):
                    try:
                        response=client.get(url,headers={'X-Chat-Service-Token':token})
                        if response.status_code==expected: break
                    except httpx.HTTPError: pass
                    time.sleep(1)
                else: raise ValueError('Service not ready before paid dispatch')
            status=client.get('http://127.0.0.1:8101/api/v1/status',headers={'X-Chat-Service-Token':token}).json()
            if (status.get('llm') or {}).get('default_model')!=MODEL: raise ValueError('Snapshot not configured')
        args=paired.args_parse(['--output',str(FOLDER),'--concurrency','1','--timeout','140','--max-retries','0','--max-backoff','5','--requests-per-minute','20',
             '--max-provider-calls','1200','--blocks',str(len({r['session_id'] for r in rows})),'--chat-url','http://127.0.0.1:8101/api/v1','--filter-url','http://127.0.0.1:8100/api/v1'])
        args.mcp_snapshot=ROOT/'chat-service/app/lib/shop_knowledge.py'; args.history_db=Path(env['SQLITE_DB_PATH'])
        runner=StagedRunner(args,FOLDER,ordered,pilot,gateway)
        runner.run()
    except BaseException as exc:
        failure={'type':type(exc).__name__,'message':str(exc)}; dump(OUT/'e2_results/execution_stop.json',failure)
        print('EXECUTION STOP '+str(failure),flush=True)
    finally:
        if runner:
            if runner.must_restore: runner.restore()
            runner.close()
        with httpx.Client(timeout=10,trust_env=False) as client:
            state=client.get('http://127.0.0.1:8101/api/v1/security/state',headers={'X-Chat-Service-Token':token})
            data=state.json()
            dump(OUT/'e2_results/post-execution-security-state.json',{'http':state.status_code,'data':data,'verified':paired.state_flags(data)==(True,True)})
        dump(OUT/'e2_results/final-budget.json',gateway.snapshot())
        for p in reversed(processes):
            try:
                parent=psutil.Process(p.pid); children=parent.children(recursive=True)
                for child in children: child.terminate()
                parent.terminate(); psutil.wait_procs(children+[parent],timeout=5)
            except psutil.NoSuchProcess: pass
        for stream in streams: stream.close()
        verify(); science.verify_freeze(FOLDER)
        if sha((ROOT/'scripts/synthetic_v9_oracles.py').read_bytes())!=binding['oracle_sha256']: raise ValueError('Oracles changed')
    return 2 if failure else 0

if __name__=='__main__': raise SystemExit(main())
