"""Research-only detector evaluation. Never invokes a generative provider."""
import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.holdout_curation_v9 import read, write


def validate(corpus, manifest):
    m = json.loads(Path(manifest).read_text(encoding='utf-8'))
    if m.get('status') != 'E1_HOLDOUT_READY' or m.get('corpus_sha256') != hashlib.sha256(Path(corpus).read_bytes()).hexdigest():
        raise ValueError('Approval manifest/corpus mismatch')
    rows = read(corpus)
    if not rows or any(r.get('approval_status') != 'APPROVED' for r in rows):
        raise ValueError('Unapproved corpus')
    return rows


def summarize(rows):
    valid = [r for r in rows if r['status'] == 'VALID']
    counts = {k: 0 for k in ('TP', 'FP', 'TN', 'FN')}
    for r in valid:
        key = ('TP' if r['blocked'] else 'FN') if r['kind']=='attack' else ('FP' if r['blocked'] else 'TN')
        counts[key] += 1
    attacks = counts['TP']+counts['FN']
    benign = counts['FP']+counts['TN']
    groups = defaultdict(list)
    for r in valid:
        groups[(r['source'], r['family_id'])].append(r)
    rng = random.Random(42)
    intervals = {}
    for name, kind in [('recall', 'attack'), ('false_positive_rate', 'benign')]:
        clusters = [[r for r in g if r['kind']==kind] for g in groups.values()]
        clusters = [g for g in clusters if g]
        estimates = []
        if len(clusters) >= 2:
            for _ in range(1000):
                sample = [r for g in rng.choices(clusters, k=len(clusters)) for r in g]
                estimates.append(sum(r['blocked'] for r in sample)/len(sample))
            estimates.sort()
        intervals[name] = [estimates[24], estimates[974]] if estimates else None
    layers = {}
    for field in ('heuristic_blocked', 'ml_blocked'):
        observed = [r for r in rows if type(r.get(field)) is bool]
        tp = sum(r['kind']=='attack' and r[field] for r in observed)
        fp = sum(r['kind']=='benign' and r[field] for r in observed)
        na = sum(r['kind']=='attack' for r in observed)
        nb = sum(r['kind']=='benign' for r in observed)
        layers[field] = dict(observed=len(observed), skipped_or_unknown=len(rows)-len(observed),
                             TP=tp, FN=na-tp, FP=fp, TN=nb-fp,
                             recall=tp/na if na else None, false_positive_rate=fp/nb if nb else None,
                             interpretation='Conditional on layer execution; not standalone detector evaluation')
    return dict(cases=len(rows), valid_cases=len(valid), technical_failures=sum(r['status']=='TECHNICAL_FAILURE' for r in rows),
                unknown=sum(r['status']=='UNKNOWN' for r in rows), confusion_matrix=counts,
                attack_denominator=attacks, benign_denominator=benign,
                recall=counts['TP']/attacks if attacks else None,
                false_positive_rate=counts['FP']/benign if benign else None,
                cluster_bootstrap_ci95=intervals,
                layer_metrics=layers,
                interval_unit='declared source/family clusters; no automatic independence certification',
                interpretation='Detector veto only; GUARDED is not veto; no Shop attack success measured')


def infer(case, filt):
    row = {k: case[k] for k in ('id', 'kind', 'source', 'family_id')}
    row.update(text_sha256=case.get('text_sha256'), original_ids_json=case.get('original_ids_json'),
               context_reference=case.get('context_reference'))
    try:
        res = filt.analyze(case['text'])
        row.update(decision=res.decision, blocked=res.blocked, heuristic_blocked=res.heuristic.blocked,
                   heuristic_score=res.heuristic.score, ml_blocked=res.ml.blocked if res.ml else None,
                   ml_probability=res.ml.probability if res.ml else None,
                   filter_latency_ms=res.latency_ms, heuristic_latency_ms=res.heuristic_latency_ms,
                   ml_latency_ms=res.ml_latency_ms, ml_status=res.merged_features.get('ml_status'),
                   status='TECHNICAL_FAILURE' if res.merged_features.get('ml_failed') or res.merged_features.get('ml_status')=='UNAVAILABLE_NOT_TRAINED' else 'VALID' if res.decision in {'ALLOWED','BLOCKED','GUARDED'} else 'UNKNOWN')
        return row, asdict(res)
    except Exception as exc:
        row.update(status='TECHNICAL_FAILURE', blocked=None, error_type=type(exc).__name__)
        return row, None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--reprocess-only', action='store_true')
    p.add_argument('--corpus', type=Path)
    p.add_argument('--manifest', type=Path)
    p.add_argument('--evidence', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    if a.reprocess_only:
        if not a.evidence:
            p.error('--evidence required')
        results = [r['result'] for r in read(a.evidence)]
    else:
        if not a.corpus or not a.manifest:
            p.error('--corpus and --manifest required')
        cases = validate(a.corpus, a.manifest)
        if a.dry_run:
            print(json.dumps(dict(status='DRY_RUN_OK', cases=len(cases), openai_calls=0)))
            return 0
        from scripts.scientific_evaluation import frozen_files
        before = frozen_files(ROOT)
        from promption.filter.ensemble_filter import EnsembleFilter
        filt = EnsembleFilter()
        results = []
        with (a.output/'E1_evidence.jsonl').open('x', encoding='utf-8') as f:
            for c in cases:
                row, raw = infer(c, filt)
                results.append(row)
                f.write(json.dumps(dict(result=row, layer_evidence=raw), ensure_ascii=False)+'\n')
                f.flush()
        if before != frozen_files(ROOT):
            raise ValueError('Frozen detector/code/config changed during E1 execution; evidence retained, run invalid')
    fields = sorted({k for r in results for k in r})
    with (a.output/'E1_case_results.csv').open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(results)
    for key in ('family_id', 'source'):
        grouped = defaultdict(list)
        for r in results:
            grouped[(r['source'], r[key])].append(r)
        metrics = [dict(source=s, group=g, **summarize(rs)) for (s,g),rs in grouped.items()]
        for r in metrics:
            for k,v in list(r.items()):
                if isinstance(v, dict): r[k] = json.dumps(v)
        write(a.output/('E1_family_metrics.csv' if key=='family_id' else 'E1_source_metrics.csv'), metrics)
    summary = summarize(results)
    with (a.output/'E1_summary.json').open('x', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    inputs = [a.evidence] if a.reprocess_only else [a.corpus, a.manifest]
    from scripts.scientific_evaluation import frozen_files
    hashes = {str(x): hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs if x}
    for x in frozen_files(ROOT):
        path = Path(x)
        if not path.is_absolute(): path = ROOT/path
        if path.is_file(): hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    with (a.output/'E1_execution_manifest.json').open('x', encoding='utf-8') as f:
        json.dump(dict(inputs_and_code_sha256=hashes, openai_calls=0, mode='reprocess' if a.reprocess_only else 'local_filter'),f,indent=2)
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
