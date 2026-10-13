"""Reproducible session sampling and observed full-chat stage diagnostics."""
import random
from collections import Counter

STAGES = ('input_filter', 'conversation_guard', 'scope', 'generation', 'tools', 'output_guard')


def sample_sessions(cases, messages, seed=42, weights=(50, 40, 10)):
    """Sample whole sessions; template expansion preserves original multi-turn content."""
    if messages <= 0 or any(w < 0 for w in weights) or not sum(weights):
        raise ValueError('Positive messages and nonnegative, nonzero weights required')
    units, grouped = [], {}
    for case in cases:
        group = case.get('conversation_group')
        if group:
            if group not in grouped:
                grouped[group] = []
                units.append(grouped[group])
            grouped[group].append(case)
        else:
            units.append([case])
    weight = dict(zip(('benign', 'attack', 'policy'), weights))
    kind_counts = Counter(c['kind'] for c in cases)
    rng = random.Random(seed)
    selected, round_index = [], 0
    while len(selected) < messages:
        candidates = list(units)
        if candidates and len(selected) < messages:
            probabilities = [sum(weight[c['kind']] / kind_counts[c['kind']] for c in unit) / len(unit) if len(unit) <= messages - len(selected) else 0 for unit in candidates]
            if not sum(probabilities):
                raise ValueError('Requested count cannot preserve complete conversations with selected weights')
            index = rng.choices(range(len(candidates)), weights=probabilities, k=1)[0]
            unit = candidates.pop(index)
            for turn, original in enumerate(unit):
                case = dict(original)
                case.update(id=f"{original['id']}-rep-{round_index}", family_id=original.get('family_id', original['id']),
                            seed_id=original['id'], turn_index=turn, repetition=round_index)
                if original.get('conversation_group'):
                    case['conversation_group'] = f"{original['conversation_group']}-rep-{round_index}"
                selected.append(case)
        if not any(len(unit) <= messages-len(selected) and any(weight[c['kind']] for c in unit) for unit in units) and len(selected) < messages:
            raise ValueError('Requested count cannot preserve complete conversations with selected weights')
        round_index += 1
    return selected


def diagnostics(record):
    data = record.get('chat', {}).get('data') or {}
    metrics = data.get('execution_metrics') or {}
    stages = metrics.get('stages') or {}
    result = {}
    for name in STAGES:
        stage = stages.get(name) or {}
        result[name + '_stage_status'] = stage.get('status')
        result[name + '_stage_latency_ms'] = stage.get('latency_ms')
    scope = data.get('scope') or {}
    layers = data.get('filter_layers') or {}
    for name in ('heuristic', 'ml', 'ensemble', 'conversation'):
        layer = layers.get(name) or {}
        result['chat_' + name + '_blocked'] = layer.get('blocked')
        result['chat_' + name + '_status'] = layer.get('status')
        result['chat_' + name + '_score'] = layer.get('probability') if name == 'ml' else layer.get('score')
    result.update(scope_reason=scope.get('reason'), scope_expected=record['case'].get('expected_scope'),
                  scope_actual=scope.get('classification'), scope_model=metrics.get('scope_model'),
                  conversation_id=record.get('conversation_id'), turn_index=record['case'].get('turn_index'),
                  family_id=record['case'].get('family_id', record['case']['id']),
                  authenticated=record.get('user', {}).get('authenticated'),
                  expected_tools_match=None, tools_audited_count=None, tools_allowed_count=None,
                  tools_denied_count=None, permissions_reason=data.get('reason') if data.get('block_type') in ('permission', 'policy', 'rbac') else None)
    result['filter_skipped'] = data.get('filter_skipped')
    result['guard_direction'] = data.get('guard_direction')
    result['guard_reason'] = data.get('guard_reason')
    result['guard_policy_id'] = data.get('guard_policy_id')
    result['output_guard_skipped_actual'] = data.get('output_guard_skipped')
    audit = data.get('audit')
    if isinstance(audit, list):
        result['tools_audited_count'] = len(audit)
        result['tools_allowed_count'] = sum(a.get('allowed') is True for a in audit if isinstance(a, dict))
        result['tools_denied_count'] = sum(a.get('allowed') is False for a in audit if isinstance(a, dict))
        expected = record['case'].get('expected_tools')
        if expected:
            allowed = {a.get('tool') for a in audit if isinstance(a, dict) and a.get('allowed') is True}
            result['expected_tools_match'] = set(expected).issubset(allowed)
    result['scope_expected_match'] = result['scope_actual'] == result['scope_expected'] if result['scope_expected'] is not None and result['scope_actual'] is not None else None
    return result


def stage_summary(rows):
    output = {}
    for name in STAGES:
        statuses = Counter(r.get(name + '_stage_status') or 'unreported' for r in rows)
        latencies = sorted(r[name + '_stage_latency_ms'] for r in rows if isinstance(r.get(name + '_stage_latency_ms'), (int, float)))
        output[name] = {'statuses': dict(statuses), 'latency_observations': len(latencies),
                       'latency_ms': {str(p): latencies[int((len(latencies)-1)*p/100)] if latencies else None for p in (50, 95, 99)}}
    output['scope_labels'] = dict(Counter(r.get('scope_actual') or 'unreported' for r in rows))
    output['mcp_audit'] = {k: sum(r[k] for r in rows if isinstance(r.get(k), int)) for k in ('tools_audited_count', 'tools_allowed_count', 'tools_denied_count')}
    output['mcp_audit']['cases_with_audit'] = sum(r.get('tools_audited_count') is not None for r in rows)
    output['scope_labeled_cases'] = sum(r.get('scope_expected_match') is not None for r in rows)
    output['scope_mismatches'] = sum(r.get('scope_expected_match') is False for r in rows)
    return output
