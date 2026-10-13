"""Reconcile paired chat benchmark decisions without treating technical failures as detections.

Read-only post-hoc audit: no network calls, no training or model invocation.
Family counts are descriptive for repeated synthetic templates, not independent trials.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

TECHNICAL = frozenset({'guard_unavailable', 'scope_unavailable', 'scope_timeout',
                       'scope_truncated', 'invalid_scope_response',
                       'output_guard_unavailable', 'model_unavailable'})
FUNCTIONAL = frozenset({'tool_no_progress', 'attachment_unavailable'})


def read_rows(csv_file):
    with open(csv_file, encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    required = {'arm','id','kind','blocked','reason','usage_complete','known_total_tokens'}
    if not rows or not required <= set(rows[0]):
        raise ValueError('Missing paired benchmark columns: ' + ','.join(sorted(required - set(rows[0]) if rows else required)))
    return rows


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['arm']].append(row)
    result = {'methodology': 'descriptive; repeated templates; no independent confidence intervals',
              'arm_summaries': {}, 'by_family': {},
              'warning': 'No protection arm is an unconstrained LLM; no hidden-canary ASR measured.'}
    for arm, items in sorted(groups.items()):
        kinds = Counter(row['kind'] for row in items)
        blocked = Counter(row['kind'] for row in items if row['blocked'].lower() == 'true')
        tech = [row for row in items if (row['reason'] or '').casefold() in TECHNICAL]
        untracked = [row for row in items if row['usage_complete'].lower() != 'true']
        known_tokens = sum(int(float(row['known_total_tokens'])) for row in items
                           if row['known_total_tokens'] not in ('', 'null', None))
        result['arm_summaries'][arm] = {
            'rows': len(items), 'kinds': dict(kinds), 'blocked_by_kind': dict(blocked),
            'technical_failures': len(tech), 'technical_case_ids': [r['id'] for r in tech],
            'functional_errors': sum((r['reason'] or '').casefold() in FUNCTIONAL for r in items),
            'partial_usage_cases': len(untracked), 'known_tokens_lower_bound': known_tokens,
            'certified_total_tokens': None if untracked else known_tokens,
        }
        family_counts = defaultdict(lambda: Counter())
        for item in items:
            family = item['id'].split('-v6-', 1)[0].split('-run-',1)[0]
            family_counts[family]['n'] += 1
            family_counts[family]['blocked'] += item['blocked'].lower() == 'true'
            family_counts[family]['technical'] += (item['reason'] or '').casefold() in TECHNICAL
        result['by_family'][arm] = {k: dict(v) for k,v in sorted(family_counts.items())}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('paired_csv', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = summarize(read_rows(args.paired_csv))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    else:
        print(text)


if __name__ == '__main__':
    main()
