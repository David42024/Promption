"""Verify declared family and exact-text separation between train and final test CSVs.

A clean result is necessary but not sufficient: semantic paraphrases/translation family
identity require human review. Do not change the final holdout after inspecting scores.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


def load(file):
    with Path(file).open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError('Holdout inputs must not be empty')
    if 'family_id' not in rows[0]:
        raise ValueError('family_id is required for a group-disjoint assessment')
    return rows


def signatures(rows):
    family = set()
    text_hashes = set()
    sources = set()
    for row in rows:
        identifier = (row.get('family_id') or '').strip()
        if not identifier:
            raise ValueError('Missing family_id; cannot guarantee group-disjoint split')
        family.add(identifier)
        val = row.get('prompt') or row.get('text') or ''
        if val.strip():
            norm = re.sub(r'\s+', ' ', val.casefold()).strip()
            text_hashes.add(hashlib.sha256(norm.encode()).hexdigest())
        if row.get('source'):
            sources.add(row['source'])
    return family, text_hashes, sources


def check(train, test):
    a = signatures(train)
    b = signatures(test)
    family_overlap = a[0] & b[0]
    exact_overlap = a[1] & b[1]
    return {
        'train_rows': len(train), 'test_rows': len(test),
        'train_families': len(a[0]), 'test_families': len(b[0]),
        'families_shared': sorted(family_overlap),
        'shared_exact_text_hashes': len(exact_overlap),
        'shared_source_count': len(a[2] & b[2]),
        'declared_family_and_exact_text_disjoint': not family_overlap and not exact_overlap,
        'note': 'Cannot detect undocumented paraphrases, translations, or source-family identity; independent manual audit required.',
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train', required=True)
    parser.add_argument('--test', required=True)
    parser.add_argument('--report', type=Path)
    args=parser.parse_args()
    result=check(load(args.train),load(args.test))
    data=json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(data, encoding='utf8')
    else:
        print(data)
    return 0 if result['declared_family_and_exact_text_disjoint'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
