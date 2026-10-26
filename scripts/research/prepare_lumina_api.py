"""Freeze the complete 120-turn sanitized Lumina cohort for a fresh paired API replay."""
from collections import Counter
import argparse
import os
from pathlib import Path
import shutil

import luna_primary as shared
from prepare_corpus_repeat import combine_ledgers


def prepare(directory):
    os.umask(0o077)
    root = shared.ROOT
    previous = root / "output/precision_improvement_20261025/groq/qwen_bounded"
    parent = root / "output/corpus_repeat_140_20261024"
    protocol = shared.load(previous / "protocol.json")
    selected = [row for row in shared.load(parent / "cases_private.json") if row["corpus"] == "lumina"]
    assert len(selected) == 120
    assert Counter(row["label"] for row in selected) == {0: 60, 1: 60}
    assert len({row["id"] for row in selected}) == 120
    selected.sort(key=lambda row: shared.hashlib.sha256(("lumina-api-20261025:" + row["id"]).encode()).hexdigest())
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copy2(previous / "settings.json", directory / "settings.json")
    shared.dump(directory / "cases_private.json", selected)
    conditions = ["unprotected", "prompt_only", "promption"]
    plan = []
    for index, row in enumerate(selected):
        rotation = index % 3
        for condition in conditions[rotation:] + conditions[:rotation]:
            plan.append({"id": f"lumina_{row['id']}_{condition}", "case_id": row["id"],
                         "condition": condition})
    shared.dump(directory / "plan.json", plan)
    paths = [root / source["path"] for source in protocol["prior_ledgers"]] + [previous / "api_ledger.jsonl"]
    spent, sources = combine_ledgers(paths, directory / "prior_ledger.jsonl")
    assert spent < 7
    names = set(protocol["code_sha256"]) | {"scripts/research/prepare_lumina_api.py",
                                           "scripts/research/corpus_budget.test.mjs"}
    for field in ["compatibility_followup", "daily_quota_reason", "selected_strata",
                  "public_language_counts", "refusal_comparison", "parent_protocol_sha256"]:
        protocol.pop(field, None)
    protocol.update({"study": "precision_lumina_three_conditions", "cases": 120,
        "planned_episodes": 360, "budget_usd": 7,
        "title": "Lumina-only fresh three-condition API replay, 120 turns",
        "cohort": "All 120 Lumina turns in the previously exposed sanitized stratified cohort; no new independent holdout.",
        "selection": "All 60 source positives and 60 negatives from the frozen parent Lumina sample. No filter outcomes used to select or order cases.",
        "ordering": "Deterministic SHA256 ID order; run the three conditions consecutively per case, rotating their order. Report incomplete pairs separately if quota stops execution.",
        "plan_seed": "lumina-api-20261025", "conditions": conditions,
        "labels": "Original Lumina provisional silver labels unchanged, not adjudicated human gold.",
        "case_counts": dict(Counter(str(row["label"]) for row in selected)),
        "exfil_target_counts": {"lumina": sum(row["exfil_target"] for row in selected)},
        "parent_cases_sha256": shared.digest(parent / "cases_private.json"),
        "prior_spent_upper_usd": spent, "prior_ledgers": sources,
        "prior_ledger_sha256": shared.digest(directory / "prior_ledger.jsonl"),
        "runtime_options": {"reasoningEffort": "low", "reasoning_format": "hidden",
                            "store": False, "parallelToolCalls": False, "maxRetries": 0},
        "budget_authorization": "User explicitly lifted the previous USD2 ceiling in this conversation. This batch has a conservative USD7 cumulative implementation stop including all previous spend; no unlimited billing.",
        "stopping": "Stop on provider quota, missing usage, or the USD7 cumulative implementation ceiling. No automatic retries; preserve operational outcomes and unattempted cases separately.",
        "fresh_generation": "All three conditions use fresh Qwen calls; no historical responses substituted. Same synthetic key, tools and protective policy as the previous Qwen study.",
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
    print(shared.json.dumps({"cases": 120, "planned_episodes": 360,
                            "prior_upper_usd": spent, "exfil_targets": protocol["exfil_target_counts"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output.resolve())
