"""Run frozen paired E2 only after an actual new user budget approval is recorded."""
import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.synthetic_v9_research import ROOT, OUT, verify, dump, sha

def check_authorization(path):
    value=json.loads(path.read_text(encoding='utf-8'))
    hashes=sha((OUT/'datasets/corpus_hashes.json').read_bytes())
    if value.get('approved_by')!='USER' or value.get('protocol')!='SYNTHETIC_V9' or value.get('corpus_hash_manifest_sha256')!=hashes:
        raise ValueError('New user economic approval for this exact frozen synthetic corpus required')
    if value.get('max_usd')!=30 or value.get('max_provider_attempts')!=1200 or not value.get('user_message_reference'):
        raise ValueError('Approval must explicitly cover $30 and 1200 attempts; never inherit smoke authorization')
    return value

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true'); parser.add_argument('--authorization',type=Path,required=True)
    args=parser.parse_args()
    if not args.execute: parser.error('Paid execution requires --execute and actual new user authorization')
    check_authorization(args.authorization); verify()
    from scripts import scientific_evaluation as science
    from dotenv import dotenv_values
    import httpx
    import psutil
    folder=OUT/'e2_results/prepared'; manifest=science.verify_freeze(folder); runtime=manifest['configured_runtime']
    if sha((ROOT/'scripts/experimental_openai_budget_gateway.py').read_bytes())!=runtime['parameters']['gateway_code_sha256']: raise ValueError('Budget gateway code changed')
    env=os.environ.copy()
    for path in [ROOT/'.env',ROOT/'chat-service/.env',ROOT/'demo/.env.local']:
        if path.exists(): env.update({k:v for k,v in dotenv_values(path).items() if v})
    if not env.get('OPENAI_API_KEY'): raise ValueError('Provider key unavailable; never write it in approval or files')
    token=secrets.token_hex(32); key=secrets.token_hex(32)
    work=OUT/'e2_runtime'; work.mkdir(exist_ok=True)
    env.update(CHAT_SERVICE_TOKEN=token,VALIDATION_CHAT_TOKEN=token,PROMPTION_API_KEYS='tenant123.unitru:'+key,PROMPTION_ADMIN_API_KEYS='',
               PIF_API_KEYS='',PIF_LLM_API_KEY='',PROMPTION_API_KEY=key,PROMPTION_TENANT_ID='tenant123.unitru',PROMPTION_DEMO_MODE='false',
               FILTER_API_URL='http://127.0.0.1:8100',FILTER_API_KEY=key,TENANT_ID='tenant123.unitru',CHAT_API_URL='http://127.0.0.1:8101',
               NEXT_PUBLIC_CHAT_API_URL='http://127.0.0.1:8101',OPENAI_MODEL='gpt-5-nano',OPENAI_TOOL_MODEL='gpt-5-nano',OPENAI_REASONING_EFFORT='minimal',
               OPENAI_BASE_URL='http://127.0.0.1:3199/v1',VERCEL_AI_URL='http://127.0.0.1:3100/api/ai/',STORAGE_BACKEND='sqlite',PROMPTION_STORAGE_BACKEND='sqlite',
               SQLITE_DB_PATH=runtime['sqlite_db_path'],SECURITY_STATE_PATH=str(work/'security-state.json'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
               LLM_PROVIDER_ORDER='openai',LLM_PROVIDER_TIMEOUT_SECONDS='90',LLM_TOTAL_TIMEOUT_SECONDS='120',LLM_MAX_ATTEMPTS='1',DEBUG='false',PYTHONPATH=str(ROOT))
    node='C:/Users/USERJSSV/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'; py=str(ROOT/'.venv-review/Scripts/python.exe')
    specs=[('gateway',[py,'scripts/experimental_openai_budget_gateway.py','--execute','--ledger',str(OUT/'e2_results/openai-budget-ledger.json'),'--port','3199','--max-calls','1200','--max-usd','30'],ROOT),
           ('filter',[py,'-m','uvicorn','promption.api.main:app','--host','127.0.0.1','--port','8100'],ROOT),
           ('chat',[py,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8101'],ROOT/'chat-service'),
           ('bridge',[node,str(ROOT/'demo/node_modules/next/dist/bin/next'),'dev','-p','3100'],ROOT/'demo')]
    processes=[]; streams=[]; result_code=2
    with httpx.Client(timeout=1,trust_env=False) as client:
        for port in [3199,8100,8101,3100]:
            try:
                client.get(f'http://127.0.0.1:{port}/')
                raise ValueError('Dedicated port occupied; refusing unknown/shared runtime')
            except httpx.HTTPError: pass
    try:
        for name,command,cwd in specs:
            stream=(work/(name+'-paid.log')).open('a',encoding='utf-8'); streams.append(stream)
            process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW); processes.append(process)
        with httpx.Client(timeout=30,trust_env=False) as client:
            for url,expected in [('http://127.0.0.1:3199/budget',200),('http://127.0.0.1:8100/api/v1/health',200),('http://127.0.0.1:8101/api/v1/status',200),('http://127.0.0.1:3100/api/ai/turn',405)]:
                for attempt in range(60):
                    try:
                        response=client.get(url,headers={'X-Chat-Service-Token':token})
                        if response.status_code==expected: break
                    except httpx.HTTPError: pass
                    time.sleep(1)
                else: raise ValueError('Dedicated service readiness failed before Chat dispatch')
        plan=manifest['execution_plan']
        command=[py,'scripts/run_final_scientific_v9.py','--execute','--resume','--dedicated-instance','--output',str(folder),'--benign','100','--attack','100',
                 '--mcp-snapshot','chat-service/app/lib/shop_knowledge.py','--history-db',runtime['sqlite_db_path']]
        for key,value in plan.items(): command.extend(['--'+key.replace('_','-'),str(value)])
        result_code=subprocess.run(command,cwd=ROOT,env=env).returncode
    finally:
        try:
            with httpx.Client(timeout=5,trust_env=False) as client:
                response=client.get('http://127.0.0.1:8101/api/v1/security/state',headers={'X-Chat-Service-Token':token})
                state=response.json()
                if response.status_code==200 and (state.get('filter_enabled') is not True or state.get('output_guard_enabled') is not True):
                    client.post('http://127.0.0.1:8101/api/v1/security/state',headers={'X-Chat-Service-Token':token},json={'action':'reset'})
                    state=client.get('http://127.0.0.1:8101/api/v1/security/state',headers={'X-Chat-Service-Token':token}).json()
                dump(OUT/'e2_results/post-execution-security-state.json',state)
        except Exception as exc: dump(OUT/'e2_results/restoration-check-error.json',{'error_type':type(exc).__name__})
        for p in reversed(processes):
            try:
                parent=psutil.Process(p.pid); children=parent.children(recursive=True)
                for child in children: child.terminate()
                parent.terminate(); psutil.wait_procs(children+[parent],timeout=5)
            except psutil.NoSuchProcess: pass
        for stream in streams: stream.close()
    if (folder/'events.jsonl').exists():
        from scripts.synthetic_v9_analysis import article
        article()
    return result_code

if __name__=='__main__': raise SystemExit(main())
