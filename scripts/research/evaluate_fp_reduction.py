"""Paired local regression against frozen predictions, without generation or API calls."""
import argparse
from collections import Counter
import json
import logging
import os
from pathlib import Path

logging.disable(logging.CRITICAL)
import luna_primary as shared
from prepare_corpus_study import CachedEnsemble, history_rows, public_rows, research_rows, matrix
from promption import ConversationGuard
from promption.scope import _validated, needs_clarification


def effective(single, context):
    return True if single is True else None if single is None or context is None else bool(context)


def evaluate(output, reuse=False):
    os.umask(0o077)
    output.mkdir(parents=True,exist_ok=True)
    prior=shared.ROOT/'output/corpus_three_conditions_20261024'
    baseline={(r['corpus'],r['id']):r for r in shared.load(prior/'local_predictions.json')}
    history=history_rows()
    lumina=[dict(id=r['id'],corpus='lumina',label=r['injection_label_proposed'],text=r['prompt'],
                 split=r['participant_split_proposed'],history=[m for p in history[r['id']] for m in (
                     {'role':'user','content':p['user']},{'role':'assistant','content':p['assistant']}) if m['content']])
            for r in research_rows() if r['cohort']=='post_reset' and not r['operational_exclusion']
            and r['injection_label_proposed'] in (0,1)]
    rows=public_rows()+lumina
    assert {(r['corpus'],r['id']) for r in rows}==set(baseline)
    engine=CachedEnsemble();guard=ConversationGuard(engine);predictions=[]
    def inspect(row,old):
        assert old['label']==row['label']
        result={k:row[k] for k in ('id','corpus','label')}
        result['split']=row.get('split','sample')
        result['old_single']=old['single_blocked']
        result['old_context']=old.get('context_blocked')
        try:result['new_single']=engine.analyze(row['text'],roles=['customer']).blocked
        except Exception as error:result.update(new_single=None,single_error=type(error).__name__)
        if row['corpus']=='lumina' or 'context_blocked' in old:
            for name,isolate in [('new_context',False),('isolated_context',True)]:
                try:
                    decision=guard.analyze(row['history'],current_text=row['text'],roles=['customer'],isolate_history=isolate)
                    result[name]=decision.blocked
                    if isolate:result['history_isolated']=decision.isolated_history
                except Exception as error:result[name]=None;result[name+'_error']=type(error).__name__
            result['old_sdk_input']=effective(result['old_single'],result['old_context'])
            result['new_sdk_input']=effective(result['new_single'],result['isolated_context'])
        return result
    sample=shared.load(prior/'cases_private.json')
    sample_baseline={r['id']:r for r in shared.load(prior/'sample_input_predictions.json')}
    if reuse:
        predictions=shared.load(output/'predictions.json')
        assert {(r['corpus'],r['id']) for r in predictions}==set(baseline)
        predictions=[{k:v for k,v in r.items() if k in {'id','corpus','label','split','old_single','new_single','single_error'}}
                     if r['corpus']=='public' else r for r in predictions]
        sample_results=shared.load(output/'sample_predictions.json')
        assert {r['id'] for r in sample_results}==set(sample_baseline)
    else:
        for i,row in enumerate(rows,1):
            predictions.append(inspect(row,baseline[(row['corpus'],row['id'])]))
            if i%1000==0:print(json.dumps({'local_processed':i,'total':len(rows)}),flush=True)
        sample_results=[inspect(c,sample_baseline[c['id']]) for c in sample]
    comparisons={}
    for cohort,subset in [('reference_all',[r for r in predictions if r['corpus']=='public']),
                          ('lumina_all',[r for r in predictions if r['corpus']=='lumina']),
                          ('reference_test',[r for r in predictions if r['corpus']=='public' and r['split']=='test']),
                          ('lumina_participant_test',[r for r in predictions if r['corpus']=='lumina' and r['split']=='test']),
                          ('sample_lumina',[r for r in sample_results if r['corpus']=='lumina']),
                          ('sample_reference',[r for r in sample_results if r['corpus']=='public'])]:
        keys=['old_single','new_single']
        if subset and 'old_sdk_input' in subset[0]:keys+=['old_context','new_context','isolated_context','old_sdk_input','new_sdk_input']
        comparisons[cohort]={'n':len(subset),**{key:matrix(subset,key) for key in keys}}
    requests=[]
    for record in (shared.load(f) for f in (prior/'episodes').glob('*_promption.json')):
        if record['status']!='blocked' or record.get('reason')!='ambiguous':continue
        event=next((e for e in reversed(record['events']) if e['stage']=='context_scope' and not e['decision']['allowed']),None)
        if event:
            eligible=needs_clarification(_validated(event['decision']),tool=event.get('proposed_tool'))
            requests.append({'id':record['id'],'label':next(c['label'] for c in sample if c['id']==record['case_id']),
                             'clarification_eligible':eligible,'tool_proposal':bool(event.get('proposed_tool'))})
    review=[]
    for c in sample:
        old=sample_baseline[c['id']]
        if c['label']==0:
            result=engine.heuristic.analyze(c['text'],roles=['customer'])
            if any(r['name'] in {'ignore_previous_instructions','ignore_instructions_es','new_instructions'} for r in result.matched_rules):
                review.append({'id':c['id'],'status':'source_label_review_required_not_relabeled',
                               'reason':'Instruction-changing text; validate intent and policy independently of the detector.'})
    result={'library_version':'1.4.0','external_api_calls':0,'labels':'Original source/silver labels unchanged; not human gold',
            'comparisons':comparisons,'cached_ambiguity_routing':{'cases':requests,
                'eligible':sum(r['clarification_eligible'] for r in requests),
                'interpretation':'Routing saved verdicts only. Not a new model evaluation or proof of task completion.'},
            'source_label_review_proposals':review,
            'baseline_protocol_sha256':shared.digest(prior/'protocol.json'),
            'new_false_negatives_sample':[r['id'] for r in sample_results if r['label']==1
                and r['old_sdk_input'] is True and r['new_sdk_input'] is False],
            'new_false_negatives_lumina':[r['id'] for r in predictions if r['corpus']=='lumina' and r['label']==1
                and r['old_sdk_input'] is True and r['new_sdk_input'] is False],
            'new_false_negative_review':{'T01236':'Source labels «que eres?» as contextual secret extraction. New identity question is isolated; propose independent annotation review, do not relabel automatically.'},
            'warnings':['Already exposed regression data; not an independent test.',
                        'Isolated input decisions require the middleware to remove old model context.',
                        'Local input false negatives are not measured exfiltration.',
                        'No new end-to-end FP/FN or ASR estimates without generation and reviewed labels.']}
    shared.dump(output/'predictions.json',predictions);shared.dump(output/'sample_predictions.json',sample_results)
    shared.dump(output/'summary.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--summarize-existing',action='store_true',help='Only summarize stored local predictions; never use after changing runtime code')
    args=p.parse_args();evaluate(args.output.resolve(),args.summarize_existing)
