"""Run the same production corpus against two explicitly configured backends."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_deployed_validation import DeployedValidator, load_and_validate_cases, select_and_group_cases
from scripts.full_chat_analysis import sample_sessions


def percentile(values, q):
    """Interpolated sample percentile; small samples do not establish tail capacity."""
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (position - lo), 2)


def timing(records):
    values = [r['chat']['latency_ms'] for r in records if r['chat']['http'] == 200]
    generated = [r['chat']['latency_ms'] for r in records
                 if r['chat']['http'] == 200 and
                 (r['chat']['data'].get('execution_metrics', {}).get('generation_calls') or 0) > 0]
    return {name: {'n': len(v), 'p50_ms': percentile(v, .5), 'p95_ms': percentile(v, .95),
                   'p99_ms': percentile(v, .99)} for name, v in [('all_http_success', values), ('with_generation', generated)]}


def execute_scenario(name, args, cases, output, repeat):
    """No retries or streaming; fresh sessions per run, ordered conversation groups."""
    prefix = name.upper()
    token = os.environ.get(prefix + '_VALIDATION_CHAT_TOKEN')
    key = os.environ.get(prefix + '_VALIDATION_FILTER_KEY')
    if not token or not key:
        raise ValueError(f'Missing {prefix}_VALIDATION_CHAT_TOKEN / {prefix}_VALIDATION_FILTER_KEY')
    validator = DeployedValidator(chat_url=getattr(args, name + '_chat_url'),
                                  filter_url=getattr(args, name + '_filter_url'),
                                  demo_url=getattr(args, name + '_demo_url'),
                                  chat_token=token, filter_key=key, timeout=args.timeout,
                                  delay=args.delay, output_dir=output / name / f'repeat-{repeat}',
                                  max_provider_calls=args.max_provider_calls)
    validator.out_dir.mkdir(parents=True, exist_ok=False)
    failure = None
    try:
        checks = validator.run_preflight()
        status = next((c for c in checks if c['case'] == 'chat_status'), None)
        health = next((c for c in checks if c['case'] == 'filter_health'), None)
        if not status or status['http'] != 200 or not health or health['http'] != 200:
            raise RuntimeError('Required chat status/filter health preflight failed')
        llm = status['data'].get('llm', {})
        if not llm.get('connected') or not llm.get('providers') or set(llm['providers']) != {'openai'}:
            raise RuntimeError('Chat must report connected OpenAI-only providers')
        validator.run_cases(cases, concurrency=1)
    except BaseException as exc:
        failure = type(exc).__name__
        raise
    finally:
        try:
            rows, summary = validator.export_artifacts()
            summary.update(scenario=name, repeat=repeat, interrupted_by=failure,
                           selected_count=len(cases), finished_count=len(validator.records),
                           budget_exhausted=validator.budget_exhausted,
                           latency_percentiles=timing(validator.records))
            (validator.out_dir / 'scenario.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        finally:
            validator.close()
    return rows, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--cases', type=Path, default=ROOT / 'data/validation/deployed_cases.jsonl')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/results/validation')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--messages', type=int, help='Exact requests per environment; sample complete sessions reproducibly')
    parser.add_argument('--kind-weights', type=float, nargs=3, default=(50, 40, 10), metavar=('BENIGN', 'ATTACK', 'POLICY'))
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--delay', type=float, default=2)
    parser.add_argument('--timeout', type=float, default=130)
    parser.add_argument('--max-provider-calls', type=int, default=180)
    for name in ('local', 'incubunt'):
        for service in ('chat', 'filter', 'demo'):
            parser.add_argument(f'--{name}-{service}-url', default=os.environ.get(f'{name.upper()}_{service.upper()}_URL'))
    args = parser.parse_args(argv)
    if not args.execute and not args.dry_run:
        parser.print_help()
        return 0
    if args.repeats < 1 or args.delay < 0 or args.timeout <= 0 or args.max_provider_calls < 1 or (args.limit is not None and args.limit < 1):
        parser.error('Positive repeats, timeout, budget and limit required; delay must be nonnegative')
    if args.messages is not None and args.limit is not None:
        parser.error('Use --messages or --limit, not both')
    try:
        source_cases = load_and_validate_cases(args.cases)
        cases = sample_sessions(source_cases, args.messages, args.seed, args.kind_weights) if args.messages is not None else select_and_group_cases(source_cases, limit=args.limit, seed=args.seed)
    except ValueError as exc:
        parser.error(str(exc))
    count = len(cases) * 2 * args.repeats
    estimate = {'requests_to_chat': count, 'filter_probes': count,
                'assumed_minutes_6_to_12_seconds_per_case': [round(count * (6 + args.delay) / 60, 1), round(count * (12 + args.delay) / 60, 1)],
                'note': 'Estimate only; provider timeouts, queues, group selection and budget change duration.'}
    estimate['selected_per_environment'] = len(cases)
    estimate['distribution'] = {k: sum(c['kind'] == k for c in cases) for k in ('benign', 'attack', 'policy')}
    estimate['sampling_note'] = 'Repeated seed sessions when requested count exceeds corpus; weights influence sampling, not exact quotas.'
    print(json.dumps(estimate, indent=2))
    if args.dry_run:
        return 0
    for name in ('local', 'incubunt'):
        for service in ('chat', 'filter', 'demo'):
            if not getattr(args, name + '_' + service + '_url'):
                parser.error(f'Explicit {name} {service} URL required; frontend domain does not establish backend topology')
        for suffix in ('VALIDATION_CHAT_TOKEN', 'VALIDATION_FILTER_KEY'):
            if not os.environ.get(name.upper() + '_' + suffix):
                parser.error(f'Missing {name.upper()}_{suffix}')
    output = args.output_dir / ('environment-comparison-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'seed': args.seed, 'corpus_sha256': hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                'case_ids': [c['id'] for c in cases], 'repeats': args.repeats,
                'kind_weights': list(args.kind_weights), 'sampling': estimate['sampling_note'],
                'budget_per_scenario_repeat': args.max_provider_calls,
                'topology_verified': False, 'estimate': estimate}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'selected_cases.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cases), encoding='utf-8')
    results = []
    for repeat in range(1, args.repeats + 1):
        order = ('local', 'incubunt') if repeat % 2 else ('incubunt', 'local')
        pair = {}
        for name in order:
            rows, summary = execute_scenario(name, args, cases, output, repeat)
            pair[name] = {row['id']: row for row in rows}
            results.append(summary)
            (output / 'summary.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        with (output / f'comparison-{repeat}.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            fields = ['id', 'local_present', 'incubunt_present'] + [f'{name}_{field}' for name in ('local', 'incubunt')
                for field in ('final_blocked', 'final_confusion', 'chat_http', 'chat_client_latency_ms', 'provider_calls', 'known_total_tokens', 'usage_complete', 'actual_model')]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for case in cases:
                row = {'id': case['id'], 'local_present': case['id'] in pair['local'], 'incubunt_present': case['id'] in pair['incubunt']}
                for name in pair:
                    row.update({f'{name}_{field}': pair[name].get(case['id'], {}).get(field) for field in
                                ('final_blocked', 'final_confusion', 'chat_http', 'chat_client_latency_ms', 'provider_calls', 'known_total_tokens', 'usage_complete', 'actual_model')})
                writer.writerow(row)
    print(f'Results: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
