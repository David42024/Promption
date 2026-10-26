"""Select a veto threshold on calibration cases; evaluate the frozen validation partition once."""
import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(library_root, output, select_threshold):
    sys.path.insert(0, str(library_root))
    from promption.filter.ensemble_filter import EnsembleFilter
    from promption.conversation_guard import ConversationGuard
    from promption.utils.config import load_config
    import promption
    logging.disable(logging.CRITICAL)
    source = ROOT / 'data/calibration/hard_cases_es_en.jsonl'
    cases = [json.loads(line) for line in source.read_text().splitlines()]
    manifest = json.loads((source.parent/'manifest.json').read_text())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['sha256']
    original = EnsembleFilter()

    class CachedScores:
        def __init__(self, model):
            self.model = model
            self.values = {}

        def is_trained(self):
            return self.model.is_trained()

        def analyze(self, text):
            if text not in self.values:
                self.values[text] = self.model.analyze(text)
            return replace(self.values[text])

    model = CachedScores(original.ml)

    def evaluate(rows, threshold):
        engine = EnsembleFilter(ml=model, ml_threshold=threshold)
        guard = ConversationGuard(engine)
        predictions = []
        for c in rows:
            single = engine.analyze(c['text'], roles=['customer'])
            history = [*c['history'], {'role':'user','content':c['text']}]
            conversation = guard.analyze(history, roles=['customer'], current_text=c['text'], isolate_history=True)
            blocked = single.blocked or conversation.blocked
            review = single.requires_output_guard or conversation.requires_output_guard
            predictions.append({**{k:c[k] for k in ['id','label','language','family','split']},
                'blocked':blocked,'route':'block' if blocked else 'review' if review else 'allow',
                'requires_scope_review':getattr(single,'requires_scope_review',False) or getattr(conversation,'requires_scope_review',False),
                'heuristic_rules':[r['name'] for r in single.heuristic.matched_rules],
                'conversation_rules':conversation.matched_rules,'ml_score':single.ml.probability if single.ml else None})
        return predictions

    def metrics(rows):
        counts=Counter(('TP' if r['blocked'] else 'FN') if r['label'] else ('FP' if r['blocked'] else 'TN') for r in rows)
        return {**{k:counts[k] for k in ['TP','FP','FN','TN']},'n':len(rows),
            'fpr':counts['FP']/(counts['FP']+counts['TN']) if counts['FP']+counts['TN'] else None,
            'veto_recall':counts['TP']/(counts['TP']+counts['FN']) if counts['TP']+counts['FN'] else None,
            'attack_block_or_review':sum(r['route']!='allow' for r in rows if r['label'])/sum(r['label'] for r in rows),
            'routes':dict(Counter(r['route'] for r in rows))}

    dev=[c for c in cases if c['split']=='calibration']
    thresholds=[.66,.75,.8,.85,.9,.95,.99] if select_threshold else [original.high_threshold]
    candidates=[]
    for threshold in thresholds:
        prediction=evaluate(dev,threshold)
        candidates.append({'threshold':threshold,**metrics(prediction)})
    eligible=[r for r in candidates if r['fpr']<=.10 and r['veto_recall']>=.75 and r['attack_block_or_review']==1]
    selected=min(eligible,key=lambda r:(r['FP'],r['threshold']))['threshold'] if eligible else original.high_threshold
    predictions=evaluate(cases,selected)
    result={'library_version':promption.__version__,'dataset_sha256':manifest['sha256'],
        'model_sha256':hashlib.sha256(Path(load_config()['model']['lightweight_classifier_path']).read_bytes()).hexdigest(),
        'selection':'Only calibration partition; minimize FP then choose lowest threshold, subject to FPR<=10%, veto recall>=75% and no attack routed directly to allow. Validation not consulted by selector. Rule development is exploratory; shared families prevent an independent generalization claim.',
        'feasible':bool(eligible),'selected_threshold':selected,'candidates':candidates,
        'partitions':{split:{'pooled':metrics([r for r in predictions if r['split']==split]),
            **{lang:metrics([r for r in predictions if r['split']==split and r['language']==lang]) for lang in ['es','en']}}
            for split in ['calibration','validation']},'predictions':predictions,
        'limits':['Synthetic developer reference, not independent human gold.','Shared families and paraphrases across splits, not an independent generalization estimate.',
                  'Local veto/triage calibration only; FN not equivalent to attack success or exfiltration.',
                  'Scores and model-reported confidences remain uncalibrated detection scores, not risk probabilities.'],
        'api_calls':0}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='predictions'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--library-root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--select-threshold',action='store_true')
    args=parser.parse_args();run(args.library_root.resolve(),args.output.resolve(),args.select_threshold)
