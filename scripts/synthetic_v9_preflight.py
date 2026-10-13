"""Free real MCP dispatch and read-only local service checks, never generation."""
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.synthetic_v9_research import ROOT, OUT, read, dump, sha

async def check_mcp():
    sys.path.insert(0,str(ROOT/'chat-service'))
    from app.mcp_tools import MCPToolExecutor
    executor=MCPToolExecutor()
    snapshot=json.loads((OUT/'datasets/mcp_fixture_snapshot.json').read_text(encoding='utf-8'))['tools']
    corpus=OUT/'datasets/e2_synthetic_200.jsonl'
    rows=read(corpus if corpus.exists() else OUT/'datasets/e2_candidates.jsonl')
    evidence=[]
    for row in rows:
        tool=row['oracle']['tool']; role=row['roles']; result=await executor.execute(tool,{},role,authenticated=row['authenticated'])
        allowed=result['audit']['allowed']
        expected_allowed=row['family_id']!='restricted' and (tool in ['getBrandInfo','getShippingPolicy','getCatalogSummary'] or set(role)&{'ventas','admin'})
        if row['kind']=='attack' and tool=='getPromotions': expected_allowed=False
        data_match=result['result']==snapshot[tool] if allowed else None
        if allowed and not data_match: raise ValueError('Actual MCP result differs from frozen snapshot')
        if bool(expected_allowed)!=allowed: raise ValueError('Unexpected effective tool authorization '+row['id'])
        evidence.append({'case_id':row['id'],'text_sha256':row['text_sha256'],'tool':tool,'roles':role,'authenticated':row['authenticated'],'allowed':allowed,'audit':result['audit'],
                         'actual_result_sha256':sha(json.dumps(result['result'],sort_keys=True,ensure_ascii=False)),'snapshot_equal':data_match,'model_exposed':False})
    dump(OUT/'e2_results/mcp_free_dispatch.json',{'status':'PASS','tool_dispatches':len(evidence),'openai_calls':0,'evidence':evidence,
                                               'limitation':'MCP handler/ACL verified locally; these are not Chat trajectories or evidence of LLM exposure.'})

def check_runtime():
    import httpx
    from dotenv import dotenv_values
    values={}
    for path in [ROOT/'.env',ROOT/'chat-service/.env',ROOT/'demo/.env.local']:
        if path.exists(): values.update({k:v for k,v in dotenv_values(path).items() if v})
    token=os.environ.get('VALIDATION_CHAT_TOKEN') or os.environ.get('CHAT_SERVICE_TOKEN') or values.get('CHAT_SERVICE_TOKEN')
    headers={'X-Chat-Service-Token':token} if token else {}
    observations=[]
    with httpx.Client(timeout=3,trust_env=False) as client:
        for url in ['http://127.0.0.1:8100/api/v1/health','http://127.0.0.1:8101/api/v1/health','http://127.0.0.1:8101/api/v1/status','http://127.0.0.1:8101/api/v1/security/state']:
            try:
                response=client.get(url,headers=headers)
                try: data=response.json()
                except ValueError: data=None
                observations.append({'url':url,'http':response.status_code,'data':data})
            except httpx.HTTPError as exc: observations.append({'url':url,'http':None,'error':type(exc).__name__})
    dump(OUT/'e2_results/runtime_readiness.json',{'read_only':True,'paid_calls':0,'observations':observations,'credential_present':bool(token),'dedicated_runtime_ready':False})

if __name__=='__main__':
    asyncio.run(check_mcp()); check_runtime(); print('MCP free preflight completed; no paid calls')
