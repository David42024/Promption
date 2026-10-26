"""Freeze a full-cohort follow-up after the portable-schema compatibility defect."""
import argparse
import json
import os
from pathlib import Path
import shutil

import luna_primary as shared
from prepare_corpus_repeat import combine_ledgers


def prepare(output):
    os.umask(0o077)
    baseline=shared.ROOT/'output/precision_improvement_20261025/groq/comparison'
    previous=shared.load(baseline/'protocol.json')
    summary=shared.load(baseline/'summary.json')
    assert summary['complete'] and summary['completed_episodes']==144
    output.mkdir(parents=True,exist_ok=False)
    for name in ['settings.json','cases_private.json']:
        assert shared.digest(baseline/name)==previous['artifacts_sha256'][name]
        shutil.copy2(baseline/name,output/name)
    plan=[row for row in shared.load(baseline/'plan.json') if row['condition']=='promption']
    assert len(plan)==48 and len({row['case_id'] for row in plan})==48
    shared.dump(output/'plan.json',plan)
    ledgers=[shared.ROOT/source['path'] for source in previous['prior_ledgers']]
    ledgers.append(baseline/'api_ledger.jsonl')
    spent,sources=combine_ledgers(ledgers,output/'prior_ledger.jsonl')
    assert abs(spent-summary['total_cost_upper_usd'])<1e-9 and spent<2
    names=set(previous['code_sha256'])|{'scripts/research/prepare_portable_followup.py',
        'scripts/research/summarize_precision_study.py'}
    protocol={**previous,'study':'precision_portable_followup','library_version':'1.7.1',
        'title':'Complete 48-case protected follow-up with atomic portable attack/origin schema',
        'conditions':['promption'],'planned_episodes':48,'cases':48,
        'selection':'All 48 previously frozen cases, not just operational failures. No relabeling or outcome-based subsampling.',
        'intervention':'Encode attack and origin as one enum in portable JSON Schema; validate canonical metadata after decoding. No contradictory response is silently accepted.',
        'baseline_directory':str(baseline.relative_to(shared.ROOT)),
        'baseline_protocol_sha256':shared.digest(baseline/'protocol.json'),
        'baseline_summary_sha256':shared.digest(baseline/'summary.json'),
        'baseline_reuse':'Only the 96 original unprotected and prompt-only episodes are reused for the updated three-condition table. All 48 protected episodes are fresh. The original 144-episode candidate study is preserved separately.',
        'prior_spent_upper_usd':spent,'prior_ledgers':sources,
        'prior_ledger_sha256':shared.digest(output/'prior_ledger.jsonl'),
        'code_sha256':{name:shared.digest(shared.ROOT/name) for name in sorted(names)},
        'artifacts_sha256':{name:shared.digest(output/name) for name in ['settings.json','cases_private.json','plan.json','prior_ledger.jsonl']}}
    shared.dump(output/'protocol.json',protocol)
    for name in ['episodes','requests','api_responses','artifacts']:(output/name).mkdir()
    for name in names:
        target=output/'frozen_source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(shared.ROOT/name,target)
    print(json.dumps({'episodes':48,'prior_upper_usd':spent,'remaining_upper_usd':2-spent}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.resolve())
