"""Finish the already frozen offline E2 preparation; never rewrites corpus inputs."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.synthetic_v9_research import OUT, read, dump, verify
from scripts import scientific_evaluation as science
from scripts.run_final_scientific_v9 import request_bound

def main():
    verify(); folder=OUT/'e2_results/prepared'; manifest=science.verify_freeze(folder)
    rows=read(folder/'corpus.jsonl'); validation=science.validate_cases(rows,final=False)
    if rows!=read(OUT/'datasets/e2_synthetic_200.jsonl'): raise ValueError('Prepared and frozen corpus differ')
    args=SimpleNamespace(**manifest['execution_plan'],max_backoff=5)
    bound=request_bound(args)
    runtime=manifest['configured_runtime']
    from collections import Counter
    longest=max(Counter(r['session_id'] for r in rows).values())
    if longest*bound>=runtime['baseline_max_seconds']-20: raise ValueError('Session exceeds baseline lease')
    ready=json.loads((OUT/'e2_results/runtime_readiness.json').read_text(encoding='utf-8'))
    if not ready['dedicated_runtime_ready']: raise ValueError('Read-only runtime preflight failed')
    plan={'status':'OFFLINE_DRY_RUN_OK','protocol':'SYNTHETIC_V9','cases':len(rows),'per_class':dict(Counter(r['kind'] for r in rows)),
          'sessions':validation['sessions'],'paired_chat_traversals':400,'history_conditioned_traversals':2*sum(bool(r['history']) for r in rows),
          'reference_history_pairs':sum(len(r['history'])//2 for r in rows),'longest_session_turns':longest,'request_time_bound_seconds':bound,
          'baseline_lease_seconds':runtime['baseline_max_seconds'],'longest_session_bound_seconds':longest*bound,
          'runtime_attestation':'original services GET-only check passed with nonpaying provider credential; paid runtime must be reattested',
          'network_calls_in_offline_dry_run':0,'openai_calls':0,'execution_authorized':False,'provider_attempt_ceiling':1200,'cost_ceiling_usd':30,
          'scope_attempt_static_upper':70400,'generation_attempt_static_upper':2400,
          'upper_bound_note':'Conservative structural bounds, not forecasts: initial scope retry, five turns with up to eight proposed tools, two middleware scope texts per operation, backend tool-scope transport retries, plus final fallback. Receipts/vetoes/dedup/timeouts reduce actual calls. Gateway and runner cap dispatch at 1200 attempts regardless.',
          'paid_execution_entrypoint':'scripts/synthetic_v9_paid_execution.py --execute --authorization <actual-user-approval.json>'}
    dump(OUT/'e2_results/dry_run.json',plan)
    chars=sum(len(r['text'])+sum(len(m['content']) for m in r['history']) for r in rows)*2
    budget={'model':'gpt-5-nano','price_source':'https://developers.openai.com/api/docs/models/gpt-5-nano','verified_user_date':'2026-10-12',
            'input_usd_per_million':.05,'output_usd_per_million':.40,'cached_input_usd_per_million':.005,'cache_discount_assumed':False,
            'authorization_status':'PENDING_USER_APPROVAL','planned_chat_traversals':400,'provider_attempt_limit':1200,'monetary_limit_usd':30,
            'paired_user_history_characters':chars,'estimated_user_history_tokens_chars_div_3':round(chars/3),
            'estimated_provider_calls_low_central_high':[600,900,1200],'assumed_average_input_tokens_per_call':10000,'assumed_average_output_tokens_per_call':2000,
            'estimated_cost_low_central_high_usd':[.78,1.17,1.56],'estimated_total_input_tokens_low_central_high':[6000000,9000000,12000000],
            'estimated_total_output_tokens_low_central_high':[1200000,1800000,2400000],
            'estimate_limitation':'Assumptions for planning, not observed tokens or guaranteed completion. Includes allowance for system, schema/results, scope and reasoning; no exact tokenizer installed. Actual unknown remain null.',
            'gateway_input_upper_tokens_per_attempt':400000,'gateway_output_upper_tokens_per_attempt':6144,'gateway_reserved_usd_per_attempt':.0224576,
            'gateway_max_reserved_usd_at_call_limit':26.94912,'gateway_limit_usd':30,
            'enforcement':'Existing gateway persistent reservation before every upstream dispatch; installed OpenAI SDK honors OPENAI_BASE_URL. Function tools only, alias fixed, bounded output required. Original watchdog, leases, restore and ambiguous-intent refusal retained.',
            'stop_on':'budget/call ceiling, unknown dispatched calls, model/code/config drift, mismatched arms or failed restoration; no automatic budget extension',
            'paid_calls_observed':0}
    dump(OUT/'e2_results/budget_plan.json',budget)
    dump(OUT/'e2_results/dry_run_completion.json',{'status':'PASS','prepared_manifest_unchanged':True,'reason':'Original adapter omitted max_backoff on argparse Namespace; completed offline request-bound validation without changing frozen adapter or inputs.', 'code_sha256':science.digest(Path(__file__).read_bytes())})
    print(json.dumps(plan),flush=True)

if __name__=='__main__': main()
