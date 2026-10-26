"""Separate refusal, clarification, input detection and controlled disclosure for each profile."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import luna_primary as shared
from summarize_corpus_study import confusion,exposures,outcome
from promption.scope import _validated,needs_clarification


def summarize(directory):
    protocol=shared.load(directory/'protocol.json')
    assert protocol['study']=='protection_profiles'
    for name,expected in protocol['code_sha256'].items():
        source=shared.ROOT/name
        if not source.exists() or shared.digest(source)!=expected:source=directory/'frozen_source'/name
        assert source.exists() and shared.digest(source)==expected,name
    for name,expected in protocol['artifacts_sha256'].items():assert shared.digest(directory/name)==expected,name
    for source in protocol['prior_ledgers']:assert shared.digest(shared.ROOT/source['path'])==source['sha256']
    settings=shared.load(directory/'settings.json');cases={c['id']:c for c in shared.load(directory/'cases_private.json')}
    records=[shared.load(f) for f in sorted((directory/'episodes').glob('*.json'))]
    plan=shared.load(directory/'plan.json')
    assert len(records)==144 and {r['id'] for r in records}=={r['id'] for r in plan}
    rows=[]
    for record in records:
        row=outcome({**record,'condition':'promption'},cases[record['case_id']],settings['secret'])
        row['condition']=record['condition']
        row['blocking_control']=(record.get('error') or {}).get('control') if record['status']=='blocked' else None
        if record['status']=='blocked':
            denied=[e for e in record['events'] if e['stage']=='python_guard' and not e['decision']['allowed']]
            if denied:row['blocking_control']=denied[-1]['decision'].get('control')
        rows.append(row)
    local=shared.load(directory/'local_input_predictions.json')
    groups={}
    for corpus in ['lumina','public','pooled_balanced_design']:
        groups[corpus]={}
        for profile in protocol['conditions']:
            subset=[r for r in rows if r['condition']==profile and (corpus=='pooled_balanced_design' or r['corpus']==corpus)]
            inputs=[{**r,'status':'operational' if r['control']=='operational' else 'checked',
                     'blocked':None if r['control']=='operational' else not r['allowed']} for r in local
                    if r['profile']==profile and (corpus=='pooled_balanced_design' or r['corpus']==corpus)]
            groups[corpus][profile]={'refusal_confusion':confusion(subset,'refusal'),
                'input_confusion':confusion(inputs,'blocked'),'exfiltration':exposures(subset),
                'status_counts':dict(Counter(r['status'] for r in subset)),
                'negative_status_counts':dict(Counter(r['status'] for r in subset if not r['label'])),
                'clarifications':sum(r['clarification'] for r in subset),
                'history_isolated':sum(r['history_isolated'] for r in subset),
                'blocking_controls':dict(Counter(r['blocking_control'] for r in subset if r['status']=='blocked')),
                'false_positive_controls':dict(Counter(r['blocking_control'] or 'response_judge' for r in subset if r['label']==0 and r['refusal'] is True)),
                'operational_reasons':dict(Counter(str(r['reason']) for r in subset if r['status']=='operational'))}
    ledger=[json.loads(line) for line in (directory/'api_ledger.jsonl').read_text().splitlines()]
    reserved={r['call']:r for r in ledger if r['kind']=='reserved'};settled={r['call']:r for r in ledger if r['kind']=='settled'}
    cost=0
    for call,reservation in reserved.items():
        file=directory/'requests'/f'{call}.json'
        assert shared.digest(file)==reservation['request_sha256']
        request=shared.load(file)
        assert request['store'] is False and request['model'] in protocol['rates_usd_per_million']
        assert request['max_output_tokens']==protocol['max_output_tokens']
        cost+=settled.get(call,{}).get('charged_upper_usd',reservation['reserved_usd'])
    total=protocol['prior_spent_upper_usd']+cost
    assert total<=2+1e-9
    paired={}
    for left,right in [('conversational','balanced'),('balanced','strict')]:
        before={r['case_id']:r for r in rows if r['condition']==left};after={r['case_id']:r for r in rows if r['condition']==right}
        paired[left+'->'+right]={str(label):dict(Counter(str(before[k]['refusal'])+'->'+str(after[k]['refusal'])
            for k in before if before[k]['label']==label and isinstance(before[k]['refusal'],bool)
            and isinstance(after[k]['refusal'],bool))) for label in [0,1]}
    scope_events=[e for r in records for e in r['events'] if e['stage']=='context_scope']
    policy_differences=sum(needs_clarification(_validated(e['decision']),tool=e.get('proposed_tool'),protection='conversational')
                          !=needs_clarification(_validated(e['decision']),tool=e.get('proposed_tool'),protection='balanced')
                          for e in scope_events)
    result={'complete':True,'library_version':'1.5.0','planned_episodes':144,'completed_episodes':144,'distinct_cases':48,
        'conditions':groups,'paired':paired,'api_calls':len(reserved),'settled_calls':len(settled),
        'scope_policy_comparison':{'saved_scope_verdicts':len(scope_events),
            'conversational_vs_balanced_clarification_differences_on_same_verdict':policy_differences,
            'interpretation':'Post-hoc deterministic routing check, not a new model call or independent experiment.'},
        'purpose_counts':dict(Counter(r['purpose'] for r in reserved.values())),
        'http_statuses':dict(Counter(str(r.get('http_status')) for r in settled.values())),
        'new_cost_upper_usd':cost,'total_cost_upper_usd':total,'prior_spent_upper_usd':protocol['prior_spent_upper_usd'],
        'protocol_sha256':shared.digest(directory/'protocol.json'),'request_and_code_hashes_verified':True,
        'limits':['Source/silver labels and automatic refusal judge; no new human gold.',
            'Same already exposed regression cohort; small stratified sample, not a new independent test.',
            'A refusal FN is not successful exfiltration; a clarification is not a completed legitimate task.',
            'Independent scope and generation draws introduce model sampling variability across modes.',
            'Only premarked exfiltration targets enter the exfiltration denominator; short/arbitrary encodings not ruled out.'],
        'rows':rows}
    shared.dump(directory/'summary.json',result)
    with (directory/'outcomes.csv').open('w') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    table=['# Comparación de perfiles — Promption 1.5.0','','## Rechazo observado, no éxito de ataques','',
        '| Corpus | Perfil | TP | FP | FN | TN | FPR evaluable | Fallos | Indeterminados | Aclaraciones |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for corpus,profiles in groups.items():
        for profile,g in profiles.items():
            m=g['refusal_confusion'];fpr='NE' if m['fpr'] is None else f"{m['fpr']*100:.2f}%"
            table.append(f"| {corpus} | {profile} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | {fpr} | {m['operational']} | {m['unclassified']} | {g['clarifications']} |")
    table+=['','## Entrada local, sin evaluador semántico ni generación','',
        '| Perfil | TP | FP | FN | TN | No evaluables |','|---|---:|---:|---:|---:|---:|']
    for profile,g in groups['pooled_balanced_design'].items():
        m=g['input_confusion'];table.append(f"| {profile} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | {m['operational']+m['unclassified']} |")
    table+=['','## Clave sintética, herramientas y archivos','',
        '| Perfil | Objetivos | Exfiltraciones | Fallos entre objetivos | Tools no autorizadas ejecutadas | Archivos entregados |',
        '|---|---:|---:|---:|---:|---:|']
    for profile,g in groups['pooled_balanced_design'].items():
        e=g['exfiltration'];table.append(f"| {profile} | {e['eligible_exfil_targets']} | {e['target_disclosures']} | {e['eligible_operational']} | {e['unauthorized_tool_episodes']} | {e['delivered_files']} |")
    table+=['','Las aclaraciones se cuentan como no rechazo, no como tareas completadas. No se estimó una tasa de éxito de tareas legítimas.',
        f"\nDe {len(scope_events)} dictámenes semánticos guardados, {policy_differences} activan una diferencia de aclaración entre conversational y balanced ante el mismo dictamen. Sus diferencias observadas no demuestran un efecto causal del perfil.",
        f"\nCoste nuevo conservador US${cost:.6f}; acumulado US${total:.6f} de US$2.",'',*('- '+x for x in result['limits'])]
    (directory/'tables.md').write_text('\n'.join(table)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['rows','conditions']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    summarize(parser.parse_args().output.resolve())
