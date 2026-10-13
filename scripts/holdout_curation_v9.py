"""Offline research-only curation; recorded human claims are never inferred."""
import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def normal(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def read(path):
    p = Path(path)
    if p.suffix == '.csv':
        with p.open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').split('\n') if x.strip()]


def write(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8', newline='') as f:
        if p.suffix == '.csv':
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['id'])
            w.writeheader()
            w.writerows(rows)
        else:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')


def prepare(rows, references):
    ids, groups, normalized = set(), defaultdict(list), defaultdict(list)
    for r in rows:
        if not r.get('id') or r['id'] in ids or not r.get('source'):
            raise ValueError('Missing/colliding original ID or source')
        if not isinstance(r.get('text'), str) or not r['text'].strip() or r.get('kind') not in {'benign', 'attack'}:
            raise ValueError('Empty text or invalid source label')
        ids.add(r['id'])
        h = sha(r['text'])
        if r.get('text_sha256') and r['text_sha256'] != h:
            raise ValueError('Original text hash mismatch')
        groups[h].append(r)
        normalized[sha(normal(r['text']))].append(r['id'])
    queue = []
    for h, unit in sorted(groups.items()):
        r = unit[0]
        collision = len({(x['source'], x['kind']) for x in unit}) > 1
        queue.append(dict(id='sha256-' + h, text=r['text'], text_sha256=h,
                          normalized_sha256=sha(normal(r['text'])),
                          original_ids_json=json.dumps([x['id'] for x in unit]),
                          original_count=len(unit), source=r['source'], kind=r['kind'],
                          source_reference=references.get(r['source'], 'UNKNOWN'),
                          family_proposal=r.get('declared_group') or 'UNKNOWN', family_id='',
                          nearest_cosine=r.get('nearest_word_tfidf_cosine'),
                          exact_overlap=r.get('exact_overlap', 'UNKNOWN'),
                          cross_source_or_label_collision=collision,
                          license_proposal='MIT_DECLARED_BY_DATASET_CARD' if r['source']=='NotInject' else 'DATA_LICENSE_UNRESOLVED',
                          context_reference='', context_reviewed='',
                          license_status='PENDING_LICENSE', license_reference='',
                          provenance_reviewed='', semantic_reviewed='', independence_reviewed='',
                          reviewer_id='', review_date='', review_notes='', decision='PENDING_REVIEW'))
    return queue, dict(original_rows=len(rows), unique_exact_texts=len(groups),
                       duplicate_surplus=len(rows)-len(groups),
                       normalized_unique_texts=len(normalized),
                       duplicate_groups=sum(len(x)>1 for x in groups.values()),
                       approved=0, status='E1_HOLDOUT_PENDING')


def approved_rows(queue, originals, known):
    canonical = {r['id']: r for r in originals}
    known_texts = {normal(x.get('text') or x.get('prompt') or '') for x in known}
    known_families = {x.get('family_id') for x in known if x.get('family_id') not in {None, '', 'UNKNOWN'}}
    known_sources = {x.get('source') for x in known if x.get('source') not in {None, '', 'UNKNOWN'}}
    out, findings, seen, approved_texts = [], [], set(), set()
    for r in queue:
        if r['id'] in seen:
            raise ValueError('Repeated review group')
        seen.add(r['id'])
        ids = json.loads(r['original_ids_json'])
        linked = [canonical[i] for i in ids]
        if not linked or any(x['text'] != r['text'] or x['source'] != r['source'] or x['kind'] != r['kind'] for x in linked):
            raise ValueError('Review changed source text, source or label')
        if sha(r['text']) != r['text_sha256'] or r['id'] != 'sha256-' + r['text_sha256']:
            raise ValueError('Review hash/identity mismatch')
        actual = {i for i, x in canonical.items() if sha(x['text']) == r['text_sha256']}
        if set(ids) != actual or len(ids) != len(set(ids)):
            raise ValueError('Duplicate trace incomplete')
        status = r.get('decision', 'PENDING_REVIEW').upper()
        if status not in {'APPROVED', 'REJECTED', 'PENDING_REVIEW', 'PENDING_LICENSE', 'NEEDS_CONTEXT'}:
            raise ValueError('Unknown review decision')
        errors = []
        if status == 'APPROVED':
            for k in ('reviewer_id', 'review_date', 'review_notes', 'source_reference', 'family_id', 'license_reference'):
                if not r.get(k) or r[k] == 'UNKNOWN':
                    errors.append('missing_' + k)
            if r.get('license_status') != 'VERIFIED':
                errors.append('PENDING_LICENSE')
            for k in ('provenance_reviewed', 'semantic_reviewed', 'independence_reviewed'):
                if str(r.get(k)).lower() != 'true':
                    errors.append('missing_' + k)
            if r['kind']=='attack' and (str(r.get('context_reviewed')).lower()!='true' or not r.get('context_reference')):
                errors.append('NEEDS_CONTEXT')
            if normal(r['text']) in known_texts or r.get('family_id') in known_families or r['source'] in known_sources:
                errors.append('development_or_regression_overlap')
            if not known or any(x.get('family_id') in {None, '', 'UNKNOWN'} or x.get('source') in {None, '', 'UNKNOWN'} for x in known):
                errors.append('incomplete_known_inventory')
            if not errors:
                if normal(r['text']) in approved_texts:
                    raise ValueError('Approved normalized duplicates; adjudicate one representative')
                approved_texts.add(normal(r['text']))
                out.append({**r, 'label': int(r['kind']=='attack'), 'approval_status': 'APPROVED'})
        findings.append(dict(id=r['id'], status='INVALID_APPROVAL' if errors else status, errors=errors))
    return out, findings


def inventory(files):
    rows, issues = [], []
    for file in files:
        try:
            raw = read(file)
            file_hash = hashlib.sha256(Path(file).read_bytes()).hexdigest()
            for i, r in enumerate(raw):
                t = r.get('text') or r.get('prompt')
                if not isinstance(t, str) or not t.strip():
                    continue
                rows.append(dict(id=str(r.get('id', i)), text=t, source=r.get('source') or 'UNKNOWN',
                                 family_id=r.get('family_id') or r.get('group_id') or 'UNKNOWN',
                                 text_sha256=sha(t), file=str(file), file_sha256=file_hash,
                                 family_origin='family_id' if r.get('family_id') else 'group_id' if r.get('group_id') else 'UNKNOWN'))
        except (ValueError, OSError, UnicodeError) as e:
            issues.append(dict(file=str(file), error=type(e).__name__))
    return rows, issues


def export_e2(csv_path, converter, development, regression):
    spec = importlib.util.spec_from_file_location('reviewed_export', converter)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw = read(csv_path)
    for r in raw:
        if r.get('approval_status', '').upper() != 'APPROVED':
            continue
        if r.get('attack_entrypoint') not in {'direct_user', 'user_message'} and r.get('kind') == 'attack':
            raise ValueError('UNSUPPORTED_SURFACE: current runner only injects user messages')
        for k in ('source_commit', 'source_license_notes', 'review_date', 'expected_policy'):
            if not r.get(k) or r[k] == 'UNKNOWN':
                raise ValueError('Missing E2 review/evidence field: ' + k)
    rows = mod.build_rows(Path(csv_path))
    if any(x.get('family_id') in {None, '', 'UNKNOWN'} or x.get('source') in {None, '', 'UNKNOWN'} for x in development + regression):
        raise ValueError('Known inventories have unresolved metadata')
    from scripts.scientific_evaluation import validate_cases
    validate_cases(rows, development, regression, final=True)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'review-report', 'validate', 'export', 'inventory', 'e2-import', 'e2-export'])
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--originals', type=Path)
    p.add_argument('--known', type=Path, action='append', default=[])
    p.add_argument('--references', type=Path)
    p.add_argument('--converter', type=Path)
    p.add_argument('--development', type=Path)
    p.add_argument('--regression', type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    if a.action in {'prepare', 'review-report'}:
        rows = read(a.input)
        q, report = prepare(rows, json.loads(a.references.read_text()) if a.references else {})
        write(a.output/'originals.jsonl', rows)
        with (a.output/'original_input_copy.jsonl').open('xb') as f:
            f.write(a.input.read_bytes())
        write(a.output/'E1_REVIEW_QUEUE.csv', q)
        (a.output/'originals.sha256').write_text(hashlib.sha256((a.output/'originals.jsonl').read_bytes()).hexdigest())
    elif a.action == 'inventory':
        rows, issues = inventory(json.loads(a.input.read_text()))
        write(a.output/'inventory.jsonl', rows)
        report = dict(rows=len(rows), unknown_metadata=sum(x['source']=='UNKNOWN' or x['family_id']=='UNKNOWN' for x in rows), issues=issues)
    elif a.action == 'e2-import':
        rows = read(a.input)
        if any(not r.get('id') or not r.get('text') or not r.get('source_reference') for r in rows):
            raise ValueError('Imported E2 rows need original ID/text/source reference')
        with (a.output/'imported_review.csv').open('xb') as f:
            f.write(a.input.read_bytes())
        report = dict(status='E2_HOLDOUT_PENDING', received=len(rows), input_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest())
    elif a.action == 'e2-export':
        rows = export_e2(a.input, a.converter, read(a.development), read(a.regression))
        write(a.output/'E2_holdout.jsonl', rows)
        report = dict(status='E2_HOLDOUT_READY', rows=len(rows))
    else:
        known = [r for x in a.known for r in read(x)]
        rows, findings = approved_rows(read(a.input), read(a.originals), known)
        write(a.output/'review_findings.jsonl', findings)
        invalid = any(x['status']=='INVALID_APPROVAL' for x in findings)
        report = dict(status='E1_HOLDOUT_READY' if rows and not invalid else 'E1_HOLDOUT_PENDING', approved=len(rows), invalid_approval=invalid)
        if a.action == 'export' and rows and not invalid:
            write(a.output/'E1_holdout.jsonl', rows)
            report.update(corpus_sha256=hashlib.sha256((a.output/'E1_holdout.jsonl').read_bytes()).hexdigest(),
                          sources=sorted({r['source'] for r in rows}), reviewers=sorted({r['reviewer_id'] for r in rows}),
                          exclusions=len(findings)-len(rows), review_file_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest())
            with (a.output/'E1_APPROVAL_MANIFEST.json').open('x', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
    with (a.output/'status.json').open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report))
    return 0 if report.get('status', '').endswith('READY') or a.action in {'prepare', 'review-report', 'inventory', 'e2-import'} else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        raise SystemExit(2)
