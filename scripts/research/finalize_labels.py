"""Build gold metrics and retraining files only from explicit independent reviews."""
import argparse
import collections
import csv
import json
from pathlib import Path
import sys
from analyze_export import csv_write, matrix


def binary(value):
    value=str(value).strip()
    if value not in ['0','1','U','']:
        raise ValueError('Reviewer labels must be 0, 1, U or blank.')
    return int(value) if value in ['0','1'] else None


def finalize(dataset, review, output):
    rows={r['id']:r for r in map(json.loads,dataset.read_text().splitlines())}
    with review.open(encoding='utf-8-sig',newline='') as stream:
        reviews=list(csv.DictReader(stream))
    if len({r['id'] for r in reviews})!=len(reviews):
        raise ValueError('Duplicate review IDs.')
    if any(r['id'] not in rows for r in reviews):
        raise ValueError('Unknown review IDs.')
    gold=[];pairs=[];unresolved=0
    for review in reviews:
        a,b=binary(review.get('reviewer_1_label','')),binary(review.get('reviewer_2_label',''))
        chosen=binary(review.get('adjudicated_injection_label',''))
        policy=binary(review.get('adjudicated_policy_label',''))
        if a is not None and b is not None:
            pairs.append((a,b))
        if chosen is None and a is not None and a==b:
            chosen=a
        if chosen is not None and (a is None or b is None or (a!=b and not review.get('review_notes','').strip())):
            raise ValueError('Gold labels require two independent labels and a rationale for adjudicated disagreement.')
        if chosen is None:
            unresolved+=1;continue
        row={**rows[review['id']],'injection_label_gold':chosen,'policy_violation_gold':policy,'annotation_status':'HUMAN_REVIEWED','review_notes':review.get('review_notes','')}
        gold.append(row)
    output.mkdir(parents=True,exist_ok=True)
    (output/'gold_labels.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in gold))
    assessed=[r for r in gold if r['cohort']=='post_reset' and not r['operational_exclusion']]
    observed=sum(a==b for a,b in pairs)/len(pairs) if pairs else None
    a_counts=collections.Counter(a for a,b in pairs);b_counts=collections.Counter(b for a,b in pairs)
    expected=sum(a_counts[k]*b_counts[k] for k in [0,1])/len(pairs)**2 if pairs else None
    kappa=(observed-expected)/(1-expected) if pairs and expected!=1 else None
    metrics={'gold_rows':len(gold),'unresolved_rows':unresolved,'double_annotated_binary_rows':len(pairs),'observed_agreement':observed,'cohen_kappa':kappa,
      'input_filter':matrix(assessed,'injection_label_gold','filter_prediction'),'request_denial_policy':matrix(assessed,'policy_violation_gold','request_denial_prediction')}
    for name in ['input_filter','request_denial_policy']:
        metrics[name]['annotation_status']='HUMAN_REVIEWED'
    (output/'gold_metrics.json').write_text(json.dumps(metrics,indent=2))
    candidates=[]; seen=set()
    conflicts={r['prompt'] for r in gold if len({v['injection_label_gold'] for v in gold if v['prompt']==r['prompt']})>1}
    for r in gold:
        if r['context_required'] or r['intent_category'] in ['technical_fixture','unintelligible','spam_or_flood'] or r.get('split_proposed') not in ['train','validation','test'] or r['prompt'] in seen or r['prompt'] in conflicts:
            continue
        label=r['injection_label_gold'];seen.add(r['prompt'])
        reviewed_type=r['intent_category'] if label and r.get('injection_label_proposed')==1 else 'reviewed_attack' if label else 'benign'
        candidates.append({'prompt':r['prompt'],'label':label,'dataset':'Custom' if label else 'Benigno','attack_type':reviewed_type,'category':reviewed_type,'source':'human_competition_20261022_reviewed','group_id':r.get('family_id',r['participant_id']),'participant_id':r['participant_id'],'split':r.get('split_proposed','UNASSIGNED'),'id':r['id']})
    csv_write(output/'reviewed_training_candidates.csv',candidates,['prompt','label','dataset','attack_type','category','source','group_id','participant_id','split','id'])
    for path in output.iterdir():
        if path.is_file():path.chmod(0o600)
    print(json.dumps({'gold_rows':len(gold),'unresolved_rows':unresolved,'cohen_kappa':kappa}))
    return metrics


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('dataset',type=Path);p.add_argument('review',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();finalize(a.dataset,a.review,a.output)
