"""Freeze an exact cohort repeat and carry all previous API consumption forward."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil

import luna_primary as shared
from prepare_corpus_study import matrix


def combine_ledgers(paths,destination):
    total=0;out=[];sources=[]
    for index,path in enumerate(paths):
        costs={}
        for line in path.read_text().splitlines():
            row=json.loads(line)
            if row['kind']=='reserved':costs[row['call']]=row['reserved_usd']
            if row['kind']=='settled':costs[row['call']]=row['charged_upper_usd']
            out.append({**row,'source_ledger':index,'source_call':row['call'],'call':f"{index}:{row['call']}"})
        total+=sum(costs.values())
        sources.append({'path':str(path.relative_to(shared.ROOT)),'sha256':shared.digest(path),'cost_upper_usd':sum(costs.values())})
    destination.write_text(''.join(json.dumps(r)+'\n' for r in out))
    return total,sources


def prepare(destination):
    os.umask(0o077)
    prior=shared.ROOT/'output/corpus_three_conditions_20261024'
    baseline=shared.load(prior/'protocol.json');summary=shared.load(prior/'summary.json')
    assert summary['complete'] and summary['completed_episodes']==720
    destination.mkdir(parents=True,exist_ok=False)
    for name in ['settings.json','cases_private.json','plan.json']:
        assert shared.digest(prior/name)==baseline['artifacts_sha256'][name]
        shutil.copy2(prior/name,destination/name)
    spent,sources=combine_ledgers([shared.ROOT/'output/api_primary_20261024/api_ledger.jsonl',prior/'api_ledger.jsonl'],destination/'prior_ledger.jsonl')
    assert abs(spent-summary['total_cost_upper_usd'])<1e-9 and spent<2
    rows=shared.load(shared.ROOT/'output/fp_reduction_20261024/predictions.json')
    local=[{**{k:r[k] for k in ('id','corpus','label','split')},'single_blocked':r['new_single'],
        **({'context_blocked':r['isolated_context']} if r['corpus']=='lumina' else {})} for r in rows]
    shared.dump(destination/'local_predictions.json',local)
    local_summary={corpus:{'n':sum(r['corpus']==corpus for r in local),
        'single':matrix([r for r in local if r['corpus']==corpus],'single_blocked'),
        'heldout_single':matrix([r for r in local if r['corpus']==corpus and r['split']=='test'],'single_blocked')}
        for corpus in ('public','lumina')}
    local_summary['lumina']['cumulative']=matrix([r for r in local if r['corpus']=='lumina'],'context_blocked')
    local_summary['context_view']='SDK isolation enabled, not the historical cumulative-only profile'
    shared.dump(destination/'local_summary.json',local_summary)
    sample=shared.load(shared.ROOT/'output/fp_reduction_20261024/sample_predictions.json')
    shared.dump(destination/'sample_input_predictions.json',[{**{k:r[k] for k in ('id','corpus','label')},
        'single_blocked':r['new_single'],'context_blocked':r['isolated_context']} for r in sample])
    protocol={**baseline,'title':'Repetición exacta de 720 episodios con Promption 1.4.0',
        'library_version':'1.4.0','prior_spent_upper_usd':spent,'prior_ledger_file':'prior_ledger.jsonl',
        'prior_ledger_sha256':shared.digest(destination/'prior_ledger.jsonl'),'prior_ledgers':sources,
        'baseline_directory':str(prior.relative_to(shared.ROOT)),'baseline_protocol_sha256':shared.digest(prior/'protocol.json'),
        'cohort':'Exact bytes of baseline cases, plan and synthetic settings; no reselection or relabeling',
        'stopping':'Shared cumulative ceiling USD2, includes both previous studies and any baseline rejudging; reserve before fetch; no retries',
        'instrumentation_changes':['Forward SDK isolateHistory to Python','Record fixed clarifications separately without generation',
                                   'Classify operational scope errors from the actual thrown decision'],
        'refusal_comparison':'Current rubric shared across all new conditions. Rejudge only old protected answered episodes with the same rubric, within the shared budget.',
        'no_new_human_gold':True,'detector_tuning':False,'regression_data_previously_exposed':True}
    names=set(baseline['code_sha256'])|{'promption/__init__.py','promption/client.py','promption/api/models.py',
        'promption/api/routes.py','promption/resources/heuristics.yaml','packages/ai-sdk/src/scope-receipts.js',
        'scripts/research/corpus_judge.mjs','scripts/research/prepare_corpus_repeat.py','scripts/research/rejudge_corpus_baseline.mjs'}
    protocol['code_sha256']={name:shared.digest(shared.ROOT/name) for name in sorted(names)}
    protocol['artifacts_sha256']={name:shared.digest(destination/name) for name in ['settings.json','cases_private.json','plan.json','prior_ledger.jsonl']}
    shared.dump(destination/'protocol.json',protocol)
    for name in ['episodes','requests','api_responses','artifacts','baseline_judgments']:(destination/name).mkdir()
    for name in names:
        target=destination/'frozen_source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(shared.ROOT/name,target)
    print(json.dumps({'planned_episodes':720,'cases':240,'prior_spent_upper_usd':spent,'remaining_upper_usd':2-spent,
                      'same_case_sha256':shared.digest(destination/'cases_private.json'),'protocol_sha256':shared.digest(destination/'protocol.json')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output.resolve())
