"""Start isolated original services with a nonpaying bridge credential; GET only."""
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.synthetic_v9_research import ROOT, OUT, dump

def main():
    import httpx
    import psutil
    from dotenv import dotenv_values
    node=Path('C:/Users/USERJSSV/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
    py=ROOT/'.venv-review/Scripts/python.exe'
    folder=OUT/'e2_runtime'; folder.mkdir(exist_ok=True)
    token=secrets.token_hex(32); key=secrets.token_hex(32)
    env=os.environ.copy()
    for path in [ROOT/'.env',ROOT/'chat-service/.env',ROOT/'demo/.env.local']:
        if path.exists(): env.update({k:v for k,v in dotenv_values(path).items() if v})
    real_key_present=bool(env.get('OPENAI_API_KEY'))
    env.update(OPENAI_API_KEY='synthetic-preflight-no-paid-provider-access',CHAT_SERVICE_TOKEN=token,
               PROMPTION_API_KEYS='tenant123.unitru:'+key,PROMPTION_ADMIN_API_KEYS='',PROMPTION_DEMO_MODE='false',PROMPTION_TENANT_ID='tenant123.unitru',
               PIF_API_KEYS='',PIF_LLM_API_KEY='',FILTER_API_URL='http://127.0.0.1:8100',PROMPTION_API_KEY=key,FILTER_API_KEY=key,
               TENANT_ID='tenant123.unitru',CHAT_API_URL='http://127.0.0.1:8101',NEXT_PUBLIC_CHAT_API_URL='http://127.0.0.1:8101',
               OPENAI_MODEL='gpt-5-nano',OPENAI_TOOL_MODEL='gpt-5-nano',OPENAI_REASONING_EFFORT='minimal',
               VERCEL_AI_URL='http://127.0.0.1:3100/api/ai/',STORAGE_BACKEND='sqlite',PROMPTION_STORAGE_BACKEND='sqlite',
               SQLITE_DB_PATH=str(folder/'conversations.db'),SECURITY_STATE_PATH=str(folder/'security-state.json'),
               HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',LLM_PROVIDER_ORDER='openai',PYTHONPATH=str(ROOT),DEBUG='false')
    specs=[('filter',[str(py),'-m','uvicorn','promption.api.main:app','--host','127.0.0.1','--port','8100'],ROOT),
           ('chat',[str(py),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8101'],ROOT/'chat-service'),
           ('bridge',[str(node),str(ROOT/'demo/node_modules/next/dist/bin/next'),'dev','-p','3100'],ROOT/'demo')]
    processes=[]; streams=[]; evidence=[]
    with httpx.Client(timeout=2,trust_env=False) as client:
        for port in [8100,8101,3100]:
            try:
                client.get(f'http://127.0.0.1:{port}/')
                raise ValueError('Dedicated port occupied; refusing to reuse unknown service')
            except httpx.HTTPError: pass
    try:
        for name,command,cwd in specs:
            stream=(folder/(name+'.log')).open('w',encoding='utf-8'); streams.append(stream)
            process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append((name,process))
        with httpx.Client(timeout=30,trust_env=False) as client:
            endpoints=[('filter','http://127.0.0.1:8100/api/v1/health'),('chat','http://127.0.0.1:8101/api/v1/health'),('status','http://127.0.0.1:8101/api/v1/status'),('security','http://127.0.0.1:8101/api/v1/security/state'),('bridge','http://127.0.0.1:3100/api/ai/turn')]
            for name,url in endpoints:
                item=None
                for attempt in range(25):
                    try:
                        response=client.get(url,headers={'X-Chat-Service-Token':token})
                        try: data=response.json()
                        except ValueError: data=None
                        item={'service':name,'url':url,'http':response.status_code,'data':data}; break
                    except httpx.HTTPError as exc:
                        item={'service':name,'url':url,'http':None,'error':type(exc).__name__}; time.sleep(1)
                evidence.append(item)
                print(json.dumps({'service':name,'http':item['http']}),flush=True)
        security=next(x for x in evidence if x['service']=='security')
        state=security.get('data') or {}
        restored=state.get('filter_enabled') is True and state.get('output_guard_enabled') is True
        ready=all(e['http']==(405 if e['service']=='bridge' else 200) for e in evidence) and restored
        dump(OUT/'e2_results/runtime_readiness.json',{'status':'READ_ONLY_PREFLIGHT_PASS' if ready else 'PREFLIGHT_FAILURE','dedicated_runtime_ready':ready,
             'observations':evidence,'real_provider_key_available_in_environment':real_key_present,'upstream_paid_access':'disabled by nonpaying credential',
             'paid_calls':0,'chat_posts':0,'state_mutations':0,'security_protected':restored,
             'limitation':'GET checks attest configured services, not inference or live OpenAI credential validity. Restart with approved bounded gateway after financial authorization.'})
    finally:
        for name,p in reversed(processes):
            try:
                parent=psutil.Process(p.pid); children=parent.children(recursive=True)
                for child in children: child.terminate()
                parent.terminate(); psutil.wait_procs(children+[parent],timeout=5)
            except psutil.NoSuchProcess: pass
        for stream in streams: stream.close()
        dump(folder/'cleanup.json',{'started_services':[n for n,p in processes],'all_started_processes_exited':all(p.poll() is not None for n,p in processes),'paid_calls':0})

if __name__=='__main__': main()
