"""Publish aggregate evaluation results without chat content or protected values."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'output/precision_improvement_20261025'


def load(path):
    return json.loads(path.read_text())


def main():
    study=load(BASE/'groq/qwen_bounded/summary.json')
    assert study['complete'] and study['completed_episodes']==48 and study['cases']==16
    candidate=load(BASE/'groq/comparison/summary.json')
    profiles=load(BASE/'profiles_171_final/summary.json')
    calibration=load(BASE/'validation_policy/selection.json')
    output=load(BASE/'known_values_before_after.json')
    fault=load(BASE/'output_fault_injection_171/summary.json')
    origins={condition:{origin:{kind:sum(row['condition']==condition and row['refusal'] is True
                and ('guard' if row['status']=='blocked' else 'generator')==origin and row['label']==label
                for row in study['rows']) for kind,label in [('TP',1),('FP',0)]}
            for origin in ['guard','generator']} for condition in ['unprotected','prompt_only','promption']}
    records=[load(path) for path in (BASE/'groq/qwen_bounded/episodes').glob('*.json')]
    tools={condition:{'native_proposals':sum(part['type']=='tool-call' for row in records if row['condition']==condition
            for event in row['events'] if event['stage']=='model_candidate' for part in event['content']),
        'mcp_calls':sum(row['tool_calls'] for row in records if row['condition']==condition),
        'created_files':sum(len(row['artifacts']) for row in records if row['condition']==condition),
        'unauthorized_effects':sum(row['unauthorized_effect'] for row in records if row['condition']==condition)}
        for condition in ['unprotected','prompt_only','promption']}
    result={'library_version':'1.7.1','date':'2026-10-25',
        'label_quality':'Original source/silver labels, development-exposed regression cohort; no new human gold.',
        'local_profiles':{key:profiles[key] for key in ['cases','executions','api_calls','cost_usd','source_sha256','model_sha256','profiles','limits']},
        'calibration':{key:calibration[key] for key in ['partition','selection','label_warning','n','counts','candidates','selected','configured_matches_selection','dataset_sha256','split_manifest_sha256','model_sha256']},
        'known_output_regression':{'kind':output['kind'],'limitation':output['limitation'],
            'counts':{key:value['counts'] for key,value in output['results'].items()}},
        'conditional_containment':{key:fault[key] for key in ['kind','library_version','source_sha256','external_api_calls','limitation','conditions']},
        'groq_three_conditions':{**{key:value for key,value in study.items() if key!='rows'},'refusal_origin_diagnostics':origins,'tools_coverage':tools},
        'previous_candidate_incomplete':{key:value for key,value in candidate.items() if key!='rows'}}
    target=ROOT/'data/results/precision_improvement_20261025.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(str(target))


if __name__=='__main__':
    main()
