"""Freeze a paired three-condition repeat within the existing cumulative USD2 ceiling."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random
import shutil

import luna_primary as shared
from prepare_corpus_repeat import combine_ledgers


def prepare(directory,provider='openai'):
    os.umask(0o077)
    previous=shared.ROOT/'output/profiles_comparison_20261025'
    protocol=shared.load(previous/'protocol.json')
    directory.mkdir(parents=True,exist_ok=False)
    for name in ['settings.json','cases_private.json']:
        assert shared.digest(previous/name)==protocol['artifacts_sha256'][name]
        shutil.copy2(previous/name,directory/name)
    cases=shared.load(directory/'cases_private.json')
    assert len(cases)==48 and Counter((c['corpus'],c['label']) for c in cases)=={
        (corpus,label):12 for corpus in ['lumina','public'] for label in [0,1]}
    conditions=['unprotected','prompt_only','promption']
    plan=[{'id':f"{c['corpus']}_{c['id']}_{condition}",'case_id':c['id'],'condition':condition}
          for c in cases for condition in conditions]
    random.Random(170020261025).shuffle(plan)
    shared.dump(directory/'plan.json',plan)
    ledger_paths=[shared.ROOT/f'output/{folder}/api_ledger.jsonl' for folder in
        ['api_primary_20261024','corpus_three_conditions_20261024','corpus_repeat_140_20261024','profiles_comparison_20261025']]
    if provider=='groq':
        ledger_paths.extend(shared.ROOT/f'output/precision_improvement_20261025/{folder}/api_ledger.jsonl'
                            for folder in ['three_conditions','groq/preflight','groq/three_conditions'])
    spent,sources=combine_ledgers(ledger_paths,directory/'prior_ledger.jsonl')
    assert spent<2
    names=set(protocol['code_sha256'])|{'promption/encoded_evidence.py','promption/assessments.py','promption/evidence.py',
        'packages/ai-sdk/src/assessments.js','scripts/research/evaluate_local_profiles.py',
        'scripts/research/calibrate_review_policy.py','scripts/research/prepare_precision_study.py',
        'promption/output_guard/known_values.py','packages/ai-sdk/src/known-values.js'}
    result={**protocol,'study':'precision_three_conditions','title':'Three conditions after development-calibrated review policies',
        'library_version':'1.7.0','provider':provider,'cases':48,'conditions':conditions,'planned_episodes':144,
        'prior_spent_upper_usd':spent,'prior_ledgers':sources,'prior_ledger_file':'prior_ledger.jsonl',
        'prior_ledger_sha256':shared.digest(directory/'prior_ledger.jsonl'),'plan_seed':170020261025,
        'selection':'Exact 48-case cohort chosen by the previous profile study before current changes; bytes unchanged. No current predictions used to select cases.',
        'policy_selection':'Review thresholds calibrated on the public val partition only. Rule development exploratory; source/silver labels unchanged.',
        'profile_assignment':'Balanced risk policy for the Promption condition. Unprotected and prompt-only use no middleware guard.',
        'semantic_variability':'Fresh model calls per condition, no response or scope cache shared across conditions.',
        'stopping':'Existing user-approved USD2 cumulative ceiling, including all prior ledgers. Reserve before fetch, no retries; operational errors never counted as security successes.',
        'primary_comparison':'Delivered synthetic-canary disclosure and unauthorized tool effects; observed refusal is a separate provisional outcome.',
        'significance':'Paired comparisons; no claim of exfiltration superiority from equal zero events. Dataset/group dependence and prior development exposure must be reported.',
        'code_sha256':{name:shared.digest(shared.ROOT/name) for name in sorted(names)},
        'artifacts_sha256':{name:shared.digest(directory/name) for name in ['settings.json','cases_private.json','plan.json','prior_ledger.jsonl']}}
    if provider=='groq':
        result.update(generation_model='openai/gpt-oss-20b',scope_model='openai/gpt-oss-120b',
                      refusal_judge_model='openai/gpt-oss-20b',concurrency=1,groq_tokens_per_minute=8000,
                      request_timeout_ms=120000,episode_timeout_ms=300000,
                      rates_usd_per_million={'openai/gpt-oss-20b':{'input':.075,'output':.3},
                                            'openai/gpt-oss-120b':{'input':.15,'output':.6}},
                      pricing_source='https://console.groq.com/docs/models',
                      provider_comparison='New Groq cohort; never pool with prior OpenAI outcomes. Same generator and tools in all three conditions.')
    shared.dump(directory/'protocol.json',result)
    for name in ['episodes','requests','api_responses','artifacts']:(directory/name).mkdir()
    for name in names:
        target=directory/'frozen_source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(shared.ROOT/name,target)
    print(json.dumps({'episodes':144,'cases':48,'prior_cost_upper_usd':spent,'remaining_ceiling_usd':2-spent,
        'case_counts':dict(Counter(c['corpus'] for c in cases))},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--provider',choices=['openai','groq'],default='openai')
    args=parser.parse_args();prepare(args.output.resolve(),args.provider)
