"""Prepare a fresh OpenAI comparison locally; never make provider requests."""
import argparse
import os
from pathlib import Path
import shutil

import luna_primary as shared
from prepare_corpus_repeat import combine_ledgers


def prepare(directory):
    os.umask(0o077)
    root = shared.ROOT
    previous = root / "output/precision_improvement_20261025/groq/lumina_120"
    protocol = shared.load(previous / "protocol.json")
    openai = shared.load(root / "output/precision_improvement_20261025/three_conditions/protocol.json")
    directory.mkdir(parents=True, exist_ok=False)
    for name in ["settings.json", "cases_private.json", "plan.json"]:
        shutil.copy2(previous / name, directory / name)
    paths = [root / source["path"] for source in protocol["prior_ledgers"]] + [previous / "api_ledger.jsonl"]
    spent, sources = combine_ledgers(paths, directory / "prior_ledger.jsonl")
    assert spent < 5
    for field in ["groq_tokens_per_minute", "groq_output_tokens_per_minute", "initial_quota_refill_ms"]:
        protocol.pop(field, None)
    names = set(protocol["code_sha256"]) | {"scripts/research/prepare_lumina_openai.py"}
    protocol.update({"provider": "openai", "study": "precision_lumina_openai_three_conditions",
        "budget_usd": 5,
        "title": "Fresh OpenAI comparison on all 120 sanitized Lumina cases",
        "prior_spent_upper_usd": spent, "prior_ledgers": sources,
        "prior_ledger_sha256": shared.digest(directory / "prior_ledger.jsonl"),
        "max_output_tokens": 1024,
        **{key: openai[key] for key in ["generation_model", "scope_model", "refusal_judge_model", "rates_usd_per_million"]},
        "runtime_options": {"reasoningEffort": "none", "store": False, "parallelToolCalls": False, "maxRetries": 0},
        "execution_state_at_preparation": "Paused at explicit user request; no OpenAI calls until the user resumes after funding.",
        "pricing_at_preparation": "Existing local OpenAI protocol rates; verify availability and prices again at execution resume.",
        "pricing_source": "Local OpenAI protocol: output/precision_improvement_20261025/three_conditions/protocol.json; verify official OpenAI pricing at resume.",
        "provider_comparison": "Fresh OpenAI responses in all three conditions. Groq results remain separate and are not substituted into the OpenAI cohort.",
        "fresh_generation": "All 360 episodes start fresh on OpenAI, with the same sanitized cases, fixtures and synthetic key. None has been executed at preparation.",
        "budget_authorization": "User resumed with OpenAI and a reduced USD5 cumulative ceiling, including all prior Groq and OpenAI spend.",
        "stopping": "Reserve before fetch; stop at USD5 cumulative, including prior spend. Keep provider failures separate; no retries of failed episodes.",
        "code_sha256": {name: shared.digest(root / name) for name in sorted(names)},
        "artifacts_sha256": {name: shared.digest(directory / name) for name in
            ["settings.json", "cases_private.json", "plan.json", "prior_ledger.jsonl"]}})
    shared.dump(directory / "protocol.json", protocol)
    for name in ["episodes", "requests", "api_responses", "artifacts"]:
        (directory / name).mkdir()
    for name in names:
        target = directory / "frozen_source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    shared.dump(directory / "preparation_status.json", {"paused": True, "external_calls": 0,
        "cases": 120, "planned_episodes": 360, "cumulative_prior_upper_usd": spent,
        "protocol_sha256": shared.digest(directory / "protocol.json")})
    print(shared.json.dumps({"paused": True, "external_calls": 0, "cases": 120,
                            "planned_episodes": 360, "prior_upper_usd": spent}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output.resolve())
