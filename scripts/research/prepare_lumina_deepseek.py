"""Freeze a fresh DeepSeek comparison without reusing any provider responses."""
import argparse
from collections import Counter
import os
from pathlib import Path
import shutil

import luna_primary as shared
from prepare_corpus_repeat import combine_ledgers


def prepare(directory, probe=False, preflight_source=None):
    os.umask(0o077)
    root = shared.ROOT
    previous = root / "output/precision_improvement_20261025/gemini/lumina_120_native"
    protocol = shared.load(previous / "protocol.json")
    directory.mkdir(parents=True, exist_ok=False)
    paths = [root / source["path"] for source in protocol["prior_ledgers"]]
    paths.append(previous / "api_ledger.jsonl")
    if not probe:
        assert preflight_source
        result = shared.load(preflight_source / "result.json")
        assert result.get("tools_ok") and result.get("roundtrip_ok") and result.get("structured_ok")
        paths.append(preflight_source / "api_ledger.jsonl")
        for name in ["settings.json", "cases_private.json", "plan.json"]:
            assert shared.digest(previous / name) == protocol["artifacts_sha256"][name]
            shutil.copy2(previous / name, directory / name)
        cases = shared.load(directory / "cases_private.json")
        assert len(cases) == 120 and Counter(row["label"] for row in cases) == {0: 60, 1: 60}
    spent, sources = combine_ledgers(paths, directory / "prior_ledger.jsonl")
    assert spent < 5
    for field in ["free_tier_only", "native_provider", "model_inventory_sha256"]:
        protocol.pop(field, None)
    names = set(protocol["code_sha256"]) | {"scripts/research/prepare_lumina_deepseek.py",
        "scripts/research/deepseek_wire.mjs", "scripts/research/deepseek_preflight.mjs",
        "scripts/research/deepseek_wire.test.mjs", "scripts/research/report_deepseek.py"}
    model = "deepseek-flash"
    protocol.update({"provider": "deepseek", "study": "deepseek_preflight" if probe else "precision_lumina_deepseek_three_conditions",
        "title": "Fresh DeepSeek-V4.1-Flash-1017 comparison on 120 sanitized Lumina cases",
        "generation_model": model, "scope_model": model, "refusal_judge_model": model,
        "expected_model_release": "DeepSeek-V4.1-Flash-1017",
        "allowed_response_models": {model: [model, "DeepSeek-V4.1-Flash-1017", "deepseek-v4.1-flash-1017"]},
        "budget_usd": 5, "prior_spent_upper_usd": spent, "prior_ledgers": sources,
        "prior_ledger_file": "prior_ledger.jsonl", "prior_ledger_sha256": shared.digest(directory / "prior_ledger.jsonl"),
        "rates_usd_per_million": {model: {"input": 0.30, "output": 1.20}},
        "max_output_tokens": 1024, "min_request_interval_ms": 0, "concurrency": 1,
        "runtime_options": {"thinking": {"type": "disabled"}, "parallelToolCalls": False, "maxRetries": 0},
        "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing/",
        "pricing_at_preparation": "Conservative peak cache-miss rates: USD0.30/M input and USD1.20/M output. Cache hits and off-peak discounts are ignored; this is an upper estimate, not an invoice.",
        "privacy": "User requested DeepSeek processing and supplied a local credential. Only the previously sanitized 120 cases, scrubbed histories and synthetic canary are sent; no names, phone numbers or real challenge key.",
        "provider_storage_control": "No store field is sent to DeepSeek; no claim about provider retention is inferred from this omission.",
        "provider_comparison": "All three conditions start with fresh DeepSeek calls. No Gemini, Groq or OpenAI outcomes are reused or pooled. Only historical cost accounting carries forward.",
        "fresh_generation": "360 fresh episodes; identical sanitized cases, fixtures, canary and protected policy.",
        "budget_authorization": "Retain the previously authorized USD5 cumulative ceiling including prior costs; provider explicitly changed by the user to DeepSeek.",
        "stopping": "Stop on missing usage, model mismatch, provider/network failure or conservative USD5 cumulative ceiling. No automatic retries of failed episodes.",
        "execution_state_at_preparation": "User authorized a fresh DeepSeek evaluation; require synthetic preflight before participant cases.",
        "execution_amendments": [],
        "instrumentation_changes": ["DeepSeek official OpenAI-compatible Chat Completions using existing AI SDK provider; no new dependency.",
            "Thinking explicitly disabled for every condition, scope evaluation and response judge.",
            "Portable JSON mode with server-side schema instructions; AI SDK still validates every structured response.",
            "Fresh output directory; historical responses are never copied."],
        "compatibility_source": str(preflight_source.relative_to(root)) if preflight_source else None,
        "code_sha256": {name: shared.digest(root / name) for name in sorted(names)},
        "artifacts_sha256": {name: shared.digest(directory / name) for name in
            (["prior_ledger.jsonl"] if probe else ["settings.json", "cases_private.json", "plan.json", "prior_ledger.jsonl"])}})
    if probe:
        protocol.update(cases=0, planned_episodes=0)
    shared.dump(directory / "protocol.json", protocol)
    for name in ["episodes", "requests", "api_responses", "artifacts"]:
        (directory / name).mkdir()
    for name in names:
        target = directory / "frozen_source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    print(shared.json.dumps({"provider": "deepseek", "preflight": probe, "model": model,
        "prior_upper_usd": spent, "cases": protocol["cases"], "planned_episodes": protocol["planned_episodes"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--preflight-source", type=Path)
    args = parser.parse_args()
    prepare(args.output.resolve(), args.probe, args.preflight_source.resolve() if args.preflight_source else None)
