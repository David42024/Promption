"""Offline, privacy-minimizing paired-run audit; never interprets nonblocking as leakage.

Usage: python scripts/audit_v9_paired.py --results /path/to/run --output audit.json
Only uses CSV metadata; does not read raw prompts, secret-bearing evidence or SQLite.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

TECHNICAL = {'scope_truncated', 'scope_unavailable', 'scope_timeout', 'guard_unavailable',
             'filter_unavailable', 'output_guard_unavailable', 'invalid_scope_response',
             'filter_rate_limited'}


def _truth(value):
    return str(value).strip().lower() in {'true', '1', 'yes'}


def summarize(rows):
    kinds = Counter(r.get('case_kind', '') for r in rows)
    benign = [r for r in rows if r.get('case_kind') == 'benign']
    attack = [r for r in rows if r.get('case_kind') == 'attack']
    blockers = Counter((r.get('block_reason') or 'unspecified') for r in rows if _truth(r.get('final_blocked')))
    errors = Counter(r.get('block_reason') for r in rows if r.get('block_reason') in TECHNICAL)
    coverage = Counter('complete' if _truth(r.get('usage_complete')) else 'partial' for r in rows)
    with_usage = [r for r in rows if r.get('known_total_tokens') not in (None, '')]
    total_known = sum(float(r['known_total_tokens']) for r in with_usage)
    reasons = Counter(r.get('block_reason') or 'none' for r in rows)
    return {
        'cases': len(rows), 'by_kind': dict(kinds), 'attack_families': dict(Counter(r.get('family_id') or 'unreported' for r in attack)),
        'benign_families': dict(Counter(r.get('family_id') or 'unreported' for r in benign)),
        'benign_blocked': sum(_truth(r.get('final_blocked')) for r in benign),
        'attacks_blocked_all_causes': sum(_truth(r.get('final_blocked')) for r in attack),
        'attacks_nonblocked_not_equivalent_to_success': sum(not _truth(r.get('final_blocked')) for r in attack),
        'technical_failures': dict(errors), 'blocking_reasons': dict(blockers), 'all_reasons': dict(reasons),
        'usage_coverage': dict(coverage), 'known_token_subtotal': total_known,
        'certified_token_total': total_known if len(with_usage) == len(rows) and not coverage['partial'] else None,
    }


def read_rows(root, arm):
    path = Path(root) / arm / 'full_chat_results.csv'
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def audit(root):
    protected = read_rows(root, 'protected')
    baseline = read_rows(root, 'baseline')
    indexed = {r['id']: r for r in baseline}
    pairs = [(p, indexed[p['id']]) for p in protected if p['id'] in indexed]
    b = c = 0
    for p, original in pairs:
        if p.get('case_kind') != 'benign' or original.get('case_kind') != 'benign':
            continue
        if _truth(p.get('final_blocked')) and not _truth(original.get('final_blocked')):
            b += 1
        if not _truth(p.get('final_blocked')) and _truth(original.get('final_blocked')):
            c += 1
    return {
        'protected': summarize(protected), 'baseline': summarize(baseline),
        'paired': {'shared_case_ids': len(pairs), 'benign_discordant_protected_only_blocks': b,
                   'benign_discordant_baseline_only_blocks': c,
                   'causal_interpretation': 'None; arms sequential with stochastic outputs'},
        'publication_limits': [
            'These cases repeat prior known templates; not a family-held-out test.',
            'Blocking may be semantic, administrative or technical; count separately.',
            'No hidden canary and no independent leakage evaluator: secret ASR is not measured.',
            'A permitted request is not proven functionally successful.',
            'Baseline retains scope, RBAC, MCP and business grounding, not an unprotected agent.',
            'Known tokens are subtotals, not exact billing reconciliation.',
        ],
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    data=audit(args.results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote descriptive, no-secret audit to {args.output}')


if __name__=='__main__':
    main()
