"""Select a deterministic smaller cohort for another Groq model after daily quota exhaustion."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random
import shutil

import luna_primary as shared
from prepare_corpus_repeat import combine_ledgers


BASE=shared.ROOT/'output/precision_improvement_20261025/groq'


def ledger_paths():
    protocol=shared.load(BASE/'comparison/protocol.json')
    return [shared.ROOT/source['path'] for source in protocol['prior_ledgers']]+[BASE/'comparison/api_ledger.jsonl']


def probe(directory):
    directory.mkdir(parents=True,exist_ok=False)
    old=shared.load(BASE/'preflight/protocol.json')
    spent,sources=combine_ledgers(ledger_paths(),directory/'prior_ledger.jsonl')
    protocol={**old,'generation_model':'qwen/qwen3.8-27b','prior_spent_upper_usd':spent,'prior_ledgers':sources,
        'prior_ledger_sha256':shared.digest(directory/'prior_ledger.jsonl'),
        'rates_usd_per_million':{'qwen/qwen3.8-27b':{'input':.8,'output':4},'openai/gpt-oss-120b':{'input':.15,'output':.6}},
        'purpose':'Synthetic Qwen tool compatibility and atomic portable context schema, excluded from study outcomes'}
    shared.dump(directory/'protocol.json',protocol)
    for name in ['requests','api_responses']:(directory/name).mkdir()
    print(json.dumps({'prior_upper_usd':spent,'remaining_upper_usd':2-spent}))


def prepare(directory):
    original=BASE/'comparison'
    previous=shared.load(original/'protocol.json')
    candidates=shared.load(original/'cases_private.json')
    selected=[]
    key=lambda row:shared.hashlib.sha256(('qwen-recovery-20261025:'+row['id']).encode()).hexdigest()
    for corpus in ['lumina','public']:
        for label in [0,1]:
            eligible=[c for c in candidates if c['corpus']==corpus and c['label']==label]
            if corpus=='lumina' and label==1:eligible=[c for c in eligible if c['exfil_target']]
            selected.extend(sorted(eligible,key=key)[:4])
    assert len(selected)==16 and Counter((c['corpus'],c['label']) for c in selected)=={
        (corpus,label):4 for corpus in ['lumina','public'] for label in [0,1]}
    directory.mkdir(parents=True,exist_ok=False)
    shutil.copy2(original/'settings.json',directory/'settings.json')
    shared.dump(directory/'cases_private.json',selected)
    conditions=['unprotected','prompt_only','promption']
    plan=[{'id':f"{c['corpus']}_{c['id']}_{condition}",'case_id':c['id'],'condition':condition}
          for c in selected for condition in conditions]
    random.Random(171020261025).shuffle(plan);shared.dump(directory/'plan.json',plan)
    paths=ledger_paths()+[BASE/'qwen_preflight/api_ledger.jsonl',BASE/'qwen_comparison/api_ledger.jsonl']
    spent,sources=combine_ledgers(paths,directory/'prior_ledger.jsonl')
    assert spent<2
    names=set(previous['code_sha256'])|{'scripts/research/prepare_groq_recovery.py','scripts/research/summarize_precision_study.py'}
    protocol={**previous,'study':'precision_groq_recovery','library_version':'1.7.1','cases':16,'planned_episodes':48,
        'title':'Three-condition 16-case Groq Qwen study after GPT-OSS daily quota exhaustion',
        'max_output_tokens':768,'groq_output_tokens_per_minute':{'qwen/qwen3.8-27b':1000},'initial_quota_refill_ms':60000,
        'compatibility_followup':'Repeat the entire fixed 16-case cohort fresh in all three conditions, with common max_output_tokens768 below the Groq1000 output-token/minute quota. The previous eight-episode candidate remains incomplete and separate. No failed response is silently replaced.',
        'generation_model':'qwen/qwen3.8-27b','refusal_judge_model':'qwen/qwen3.8-27b','scope_model':'openai/gpt-oss-120b',
        'rates_usd_per_million':{'qwen/qwen3.8-27b':{'input':.8,'output':4},'openai/gpt-oss-120b':{'input':.15,'output':.6}},
        'conditions':conditions,'plan_seed':171020261025,
        'selection':'Four cases per corpus/label cell, hash order using IDs only. Lumina positives restricted to exfiltration-target metadata. No Qwen predictions or GPT-OSS outcomes used by selector.',
        'daily_quota_reason':'GPT-OSS20B hit the Groq200000-token daily quota. Prior candidate cohort remains incomplete and separate; no conditions mix generator models.',
        'provider_comparison':'Same Qwen generator, public data, tools and protective policy across three conditions. No prior model responses reused.',
        'prior_spent_upper_usd':spent,'prior_ledgers':sources,'prior_ledger_sha256':shared.digest(directory/'prior_ledger.jsonl'),
        'code_sha256':{name:shared.digest(shared.ROOT/name) for name in sorted(names)},
        'artifacts_sha256':{name:shared.digest(directory/name) for name in ['settings.json','cases_private.json','plan.json','prior_ledger.jsonl']}}
    shared.dump(directory/'protocol.json',protocol)
    for name in ['episodes','requests','api_responses','artifacts']:(directory/name).mkdir()
    for name in names:
        target=directory/'frozen_source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(shared.ROOT/name,target)
    print(json.dumps({'cases':16,'episodes':48,'prior_upper_usd':spent,'remaining_upper_usd':2-spent}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--probe',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    (probe if args.probe else prepare)(args.output.resolve())
