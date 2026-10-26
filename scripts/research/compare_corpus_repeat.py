"""Compare protected versions with a common refusal rubric and separate clarifications."""
import argparse
from collections import Counter
import json
from pathlib import Path

import luna_primary as shared
from summarize_corpus_study import confusion, exposures, outcome


def compare(directory):
    protocol=shared.load(directory/'protocol.json')
    baseline=shared.ROOT/protocol['baseline_directory']
    assert shared.digest(baseline/'protocol.json')==protocol['baseline_protocol_sha256']
    settings=shared.load(directory/'settings.json')
    cases={c['id']:c for c in shared.load(directory/'cases_private.json')}
    old_records=[shared.load(f) for f in sorted((baseline/'episodes').glob('*_promption.json'))]
    new_records=[shared.load(f) for f in sorted((directory/'episodes').glob('*_promption.json'))]
    assert len(old_records)==len(new_records)==240
    old=[];rejudged=Counter()
    for record in old_records:
        if record['status']=='answered':
            file=directory/'baseline_judgments'/f"{record['id']}.json"
            if file.exists():
                judgment=shared.load(file)
                assert judgment['baseline_episode_sha256']==shared.digest(baseline/'episodes'/f"{record['id']}.json")
                record={**record,'refusal_prediction':judgment['refusal_prediction'],
                        'refusal_judgment':{'classification':judgment.get('classification')},
                        'judge_error':None if judgment['status']=='judged' else {'name':judgment.get('error_name')}}
                rejudged[judgment['status']]+=1
            else:
                record={**record,'refusal_prediction':None,'judge_error':{'name':'not_rejudged'}}
                rejudged['missing']+=1
        old.append(outcome(record,cases[record['case_id']],settings['secret']))
    new=[outcome(r,cases[r['case_id']],settings['secret']) for r in new_records]
    result={'comparison':'Protected 1.3.3 vs protected 1.4.0, identical cases and current refusal rubric',
        'baseline_rejudging':dict(rejudged),'human_gold':False,'conditions':{}}
    for corpus in ['lumina','public','pooled_balanced_design']:
        result['conditions'][corpus]={}
        for version,rows in [('1.3.3_rejudged',old),('1.4.0',new)]:
            subset=[r for r in rows if corpus=='pooled_balanced_design' or r['corpus']==corpus]
            result['conditions'][corpus][version]={'refusal_confusion':confusion(subset,'refusal'),
                'exfiltration':exposures(subset),'status_counts':dict(Counter(r['status'] for r in subset)),
                'negative_status_counts':dict(Counter(r['status'] for r in subset if not r['label'])),
                'clarifications':sum(r['clarification'] for r in subset),
                'history_isolated':sum(r['history_isolated'] for r in subset)}
    before={r['case_id']:r for r in old};after={r['case_id']:r for r in new}
    result['paired']={str(label):dict(Counter(str(before[k]['refusal'])+'->'+str(after[k]['refusal'])
        for k in before if before[k]['label']==label and isinstance(before[k]['refusal'],bool)
        and isinstance(after[k]['refusal'],bool))) for label in (0,1)}
    result['changed_cases']=[{'id':k,'label':before[k]['label'],'old_refusal':before[k]['refusal'],
        'new_refusal':after[k]['refusal'],'new_status':after[k]['status'],'new_reason':after[k]['reason']}
        for k in before if before[k]['refusal']!=after[k]['refusal'] or before[k]['status']!=after[k]['status']]
    result['limits']=['Source/silver labels, not adjudicated human truth.',
        'Clarifications count as non-refusals, not completed tasks.',
        'Old generation reused; only refusal judgment repeated, no old scope reexecution.',
        'One generation per case and version; sampling variability and participant dependence remain.',
        'Changes include library, scope instructions and harness forwarding; no component ablation.',
        'Input cases were already exposed during development; not a new independent test.']
    shared.dump(directory/'version_comparison.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='changed_cases'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    compare(p.parse_args().output.resolve())
