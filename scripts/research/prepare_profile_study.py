"""Freeze a prediction-blind stratified profile sample within the existing USD2 ceiling."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import shutil

import luna_primary as shared
from prepare_corpus_repeat import combine_ledgers


def select(cases):
    result=[]
    for corpus in ('lumina','public'):
        for label in (0,1):
            for stratum in (False,True):
                pool=[c for c in cases if c['corpus']==corpus and c['label']==label
                      and (bool(c.get('context_required')) if corpus=='lumina' else c['language']=='es')==stratum]
                pool.sort(key=lambda c:hashlib.sha256(('profile-20261025:'+c['id']).encode()).hexdigest())
                assert len(pool)>=6,(corpus,label,stratum)
                result.extend(pool[:6])
    assert len(result)==len({c['id'] for c in result})==48
    return result


def prepare(directory):
    os.umask(0o077)
    previous=shared.ROOT/'output/corpus_repeat_140_20261024'
    base=shared.load(previous/'protocol.json')
    summary=shared.load(previous/'summary.json')
    assert summary['complete'] and summary['completed_episodes']==720
    cases=select(shared.load(previous/'cases_private.json'))
    directory.mkdir(parents=True,exist_ok=False)
    shutil.copy2(previous/'settings.json',directory/'settings.json')
    shared.dump(directory/'cases_private.json',cases)
    conditions=['conversational','balanced','strict']
    plan=[{'id':f"{c['corpus']}_{c['id']}_{mode}",'case_id':c['id'],'condition':mode} for c in cases for mode in conditions]
    random.Random(20261025).shuffle(plan)
    shared.dump(directory/'plan.json',plan)
    paths=[shared.ROOT/'output/api_primary_20261024/api_ledger.jsonl',
           shared.ROOT/'output/corpus_three_conditions_20261024/api_ledger.jsonl',previous/'api_ledger.jsonl']
    spent,sources=combine_ledgers(paths,directory/'prior_ledger.jsonl')
    assert abs(spent-summary['total_cost_upper_usd'])<1e-9 and spent<2
    names=set(base['code_sha256'])|{'promption/profiles.py','promption/resources/config.yaml',
        'packages/ai-sdk/src/profiles.js','packages/ai-sdk/src/errors.js','packages/ai-sdk/src/transports.js',
        'scripts/research/prepare_profile_study.py'}
    protocol={**base,'study':'protection_profiles','title':'Comparación de los tres perfiles de Promption 1.5.0',
        'study_date_local':'2026-10-25','library_version':'1.5.0','conditions':conditions,'cases':48,'planned_episodes':144,
        'prior_spent_upper_usd':spent,'prior_ledger_file':'prior_ledger.jsonl',
        'prior_ledger_sha256':shared.digest(directory/'prior_ledger.jsonl'),'prior_ledgers':sources,
        'parent_cases_sha256':shared.digest(previous/'cases_private.json'),
        'parent_protocol_sha256':shared.digest(previous/'protocol.json'),
        'selection':'Deterministic SHA256(seed:case_id), 6 per corpus/label/stratum; Lumina with/without annotated context requirement, public Spanish/non-Spanish. No predictions or outcomes used.',
        'sampling_uses_filter_predictions':False,'plan_seed':20261025,
        'case_counts':{str(k):v for k,v in Counter((c['corpus'],c['label'],bool(c['history']),c['language']) for c in cases).items()},
        'selected_strata':{str(k):v for k,v in Counter((c['corpus'],c['label'],bool(c.get('context_required')) if c['corpus']=='lumina' else c['language']) for c in cases).items()},
        'public_language_counts':dict(Counter(c['language'] for c in cases if c['corpus']=='public')),
        'exfil_target_counts':dict(Counter(c['corpus'] for c in cases if c['exfil_target'])),
        'cohort':'48 cases from the already exposed 240-case regression cohort, labels unchanged; not a new independent test.',
        'profile_assignment':'Same selected profile in SDK and Python, with identical settings, ACL, model snapshots and guards.',
        'semantic_variability':'Independent scope and generation calls per episode, no cross-profile cache; differences include model sampling variation.',
        'api_confusion':'Observed refusal vs source injection label. Clarification is non-refusal, not completed task. Input-only decisions are reported separately.',
        'stopping':'Shared USD2 ceiling including all three previous ledgers; reserve before fetch, no per-call retries. Resume only unexecuted episodes after transport failures.',
        'refusal_comparison':'Current identical blind rubric across the three new profile conditions. No baseline rejudging.',
        'instrumentation_changes':['Pass profile to Python and SDK','Preserve operational control metadata'],
        'code_sha256':{name:shared.digest(shared.ROOT/name) for name in sorted(names)},
        'artifacts_sha256':{name:shared.digest(directory/name) for name in ['settings.json','cases_private.json','plan.json','prior_ledger.jsonl']}}
    for name in ['baseline_directory','baseline_protocol_sha256','strata_available','privacy_exclusions',
                 'source_hashes_previous_evaluation','sources_sha256','detection']:
        protocol.pop(name,None)
    shared.dump(directory/'protocol.json',protocol)
    for name in ['episodes','requests','api_responses','artifacts']:(directory/name).mkdir()
    for name in names:
        target=directory/'frozen_source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(shared.ROOT/name,target)
    print(json.dumps({k:protocol[k] for k in ['planned_episodes','cases','prior_spent_upper_usd','case_counts','exfil_target_counts']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.resolve())
