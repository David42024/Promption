"""Freeze a free-tier Gemini comparison with independent provider outcomes."""
import argparse
from collections import Counter
import os
from pathlib import Path
import shutil

import luna_primary as shared
from prepare_corpus_repeat import combine_ledgers


def prepare(directory, probe=False, preflight_source=None, native=False):
    os.umask(0o077)
    root = shared.ROOT
    previous = root / "output/precision_improvement_20261025/openai_lumina_120"
    protocol = shared.load(previous / "protocol.json")
    directory.mkdir(parents=True, exist_ok=False)
    paths = [root / source["path"] for source in protocol["prior_ledgers"]] + [previous / "api_ledger.jsonl"]
    preflight = preflight_source or root / ("output/precision_improvement_20261025/gemini/preflight_native" if native else
                                          "output/precision_improvement_20261025/gemini/preflight")
    prior_probes = sorted((root / "output/precision_improvement_20261025/gemini").glob("preflight*/api_ledger.jsonl"))
    paths.extend(path for path in prior_probes if path.parent != directory)
    compatible = root / "output/precision_improvement_20261025/gemini/lumina_120/api_ledger.jsonl"
    if native and compatible.exists():
        paths.append(compatible)
    if not probe:
        result = shared.load(preflight / "result.json")
        assert result.get("tools_ok") and result.get("structured_ok"), "Synthetic compatibility must pass first"
        if native:
            assert result.get("roundtrip_ok") and result.get("private_signatures_hidden")
        if preflight / "api_ledger.jsonl" not in paths:
            paths.append(preflight / "api_ledger.jsonl")
    spent, sources = combine_ledgers(paths, directory / "prior_ledger.jsonl")
    model = "gemini-3.5-flash-lite"
    listing = shared.load(root / "output/precision_improvement_20261025/gemini/models.json")
    assert any(row["name"] == "models/" + model for row in listing["models"])
    if not probe:
        for name in ["settings.json", "cases_private.json", "plan.json"]:
            shutil.copy2(previous / name, directory / name)
        cases = shared.load(directory / "cases_private.json")
        assert len(cases) == 120 and Counter(row["label"] for row in cases) == {0: 60, 1: 60}
    names = set(protocol["code_sha256"]) | {"scripts/research/prepare_lumina_gemini.py",
        "scripts/research/gemini_preflight.mjs", "scripts/research/corpus_budget.test.mjs"}
    if native:
        names |= {"packages/ai-sdk/src/provider-signatures.js", "scripts/research/package.json",
                  "scripts/research/package-lock.json", "scripts/research/gemini_native_preflight.mjs",
                  "packages/ai-sdk/package.json", "packages/ai-sdk/package-lock.json", "pyproject.toml",
                  "promption/__init__.py", "packages/ai-sdk/test/provider-signatures.test.js"}
    import promption
    version = promption.__version__
    protocol.update({"provider": "gemini-native" if native else "gemini",
        "library_version": version,
        "study": ("gemini_native_preflight" if probe else "precision_lumina_gemini_native_three_conditions") if native else
                 ("gemini_preflight" if probe else "precision_lumina_gemini_three_conditions"),
        "title": "Gemini free-tier synthetic compatibility" if probe else "Fresh Gemini comparison on 120 sanitized Lumina turns",
        "budget_usd": 5, "free_tier_only": True, "min_request_interval_ms": 15000 if probe else 6500,
        "generation_model": model, "scope_model": model, "refusal_judge_model": model,
        "max_output_tokens": 1024, "rates_usd_per_million": {model: {"input": 0, "output": 0}},
        "runtime_options": {"reasoningEffort": "minimal", "forceReasoning": False,
                            "parallelToolCalls": False, "maxRetries": 0},
        "prior_spent_upper_usd": spent, "prior_ledgers": sources,
        "prior_ledger_sha256": shared.digest(directory / "prior_ledger.jsonl"),
        "pricing_source": "https://ai.google.dev/gemini-api/docs/pricing",
        "pricing_at_preparation": "Official Gemini free-tier input/output rates are zero. User explicitly requested a free-tier project; no billing setup or paid fallback is performed. API responses do not independently attest the project billing tier.",
        "privacy": "User explicitly authorized Gemini free-tier processing after disclosure that Google may use input/output for product improvement and human review. Same sanitized 120-case sample and synthetic key; no names, phone numbers or real challenge key.",
        "provider_storage_control": "The Gemini compatibility endpoint rejects the OpenAI store field. It is omitted; no claim is made that store:false disables Google data use.",
        "provider_comparison": "Fresh Gemini calls in each condition. Previous OpenAI and Groq responses are separate; only cost accounting carries forward.",
        "fresh_generation": "All planned Gemini episodes begin fresh; no previous provider output is reused.",
        "execution_state_at_preparation": "Authorized for Gemini free tier; compatibility requires synthetic tools and structured outputs before participant data.",
        "budget_authorization": "User authorized Gemini free tier and sanitized Lumina cases, after disclosure of data usage. USD5 cumulative historical accounting ceiling retained.",
        "stopping": "Reserve before request. Stop on missing usage, provider quota, model mismatch or USD5 cumulative ceiling. No paid fallback or automatic retries of failed episodes.",
        "execution_amendments": [],
        "compatibility_source": str(preflight.relative_to(root)),
        "code_sha256": {name: shared.digest(root / name) for name in sorted(names)},
        "artifacts_sha256": {name: shared.digest(directory / name) for name in
            (["prior_ledger.jsonl"] if probe else ["settings.json", "cases_private.json", "plan.json", "prior_ledger.jsonl"])}})
    if probe:
        protocol.update(cases=0, planned_episodes=0)
    if native:
        inventory = next(row for row in listing["models"] if row["name"] == "models/" + model)
        protocol.update(runtime_options={"google": {"thinkingConfig": {"thinkingLevel": "minimal", "includeThoughts": False}}},
            allowed_response_models={model: [model, "gemini-" + inventory["version"].removeprefix("gemini-")]},
            native_provider="@ai-sdk/google@3.0.138",
            model_inventory_sha256=shared.digest(root / "output/precision_improvement_20261025/gemini/models.json"),
            instrumentation_changes=["Native Google AI SDK provider preserves genuine thought signatures.",
                "Promption 1.7.2 caches signatures privately per middleware and restores only the exact authorized tool call inside provider requests.",
                "Previous 22 compatibility episodes remain an incomplete pilot; native outcomes start fresh in all three conditions."],
            provider_comparison="Fresh native Gemini calls in every condition; no previous compatibility, OpenAI or Groq response is pooled.")
    shared.dump(directory / "protocol.json", protocol)
    for name in ["episodes", "requests", "api_responses", "artifacts"]:
        (directory / name).mkdir()
    for name in names:
        target = directory / "frozen_source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    print(shared.json.dumps({"provider": protocol["provider"], "preflight": probe, "model": model,
                            "free_tier_only": True, "prior_upper_usd": spent}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--preflight-source", type=Path)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    prepare(args.output.resolve(), args.probe, args.preflight_source.resolve() if args.preflight_source else None, args.native)
