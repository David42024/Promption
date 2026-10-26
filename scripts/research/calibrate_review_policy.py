"""Select risk policies on the existing public validation partition, never test rows."""
import argparse
from collections import Counter
import hashlib
import json
import logging
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matrix(rows, threshold):
    counts=Counter(('TP' if row['hard_veto'] or row['score'] is not None and row['score']>=threshold else 'FN')
        if row['label'] else ('FP' if row['hard_veto'] or row['score'] is not None and row['score']>=threshold else 'TN')
        for row in rows)
    return {**{key:counts[key] for key in ['TP','FP','FN','TN']},'n':len(rows),
        'fpr':counts['FP']/(counts['FP']+counts['TN']),
        'veto_recall':counts['TP']/(counts['TP']+counts['FN'])}


def run(output):
    from prepare_corpus_study import public_rows
    from promption.filter.ensemble_filter import EnsembleFilter
    from promption.utils.config import load_config
    from promption.profiles import resolve_protection
    logging.disable(logging.CRITICAL)
    rows=[row for row in public_rows() if row['split']=='val']
    assert len(rows)==658 and all(row['split']=='val' for row in rows)
    engine=EnsembleFilter()
    scored=[]
    for row in rows:
        result=engine.analyze(row['text'],roles=['customer'])
        scored.append({key:row[key] for key in ['id','label','language','group_id']}
            | {'hard_veto':result.blocked,'score':result.ml.probability if result.ml else None,
               'rules':[match['name'] for match in result.heuristic.matched_rules]})
    candidates=[{'threshold':threshold,**matrix(scored,threshold)} for threshold in [.5,.6,.66,.7,.75,.8,.85]]
    baseline=candidates[-1]
    selected={'conversational':.85}
    for profile,budget in [('balanced',.01),('strict',.03)]:
        eligible=[row for row in candidates if row['fpr']-baseline['fpr']<=budget+1e-12]
        selected[profile]=min(eligible,key=lambda row:(-row['TP'],row['FP'],-row['threshold']))['threshold']
    result={'partition':'Existing public validation only; no test rows or 240-case outcomes used by selector',
        'rule_development':'Exploratory on validation; not an independent evaluation',
        'selection':'Keep conversational at prior .85. Maximize attack veto recall subject to additional raw-source FPR <=1 percentage point balanced, <=3 strict. Break ties with fewer FP, then higher threshold.',
        'label_warning':'Raw source labels retained. Some negative labels contain explicit control overrides; these are reference conflicts for independent adjudication, not automatically relabeled.',
        'n':len(rows),'counts':dict(Counter(row['label'] for row in rows)),
        'candidates':candidates,'selected':selected,
        'configured':{profile:resolve_protection(profile).review_block_threshold for profile in selected},
        'configured_matches_selection':all(resolve_protection(profile).review_block_threshold==value for profile,value in selected.items()),
        'dataset_sha256':digest(ROOT/'data/processed/training_data.csv'),
        'split_manifest_sha256':digest(ROOT/'data/processed/split_manifest.json'),
        'model_sha256':digest(Path(load_config()['model']['lightweight_classifier_path'])),
        'script_sha256':digest(Path(__file__)),'api_calls':0}
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    (output/'scores.json').write_text(json.dumps(scored,ensure_ascii=False,indent=2))
    (output/'selection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
