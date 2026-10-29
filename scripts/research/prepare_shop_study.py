"""Freeze a balanced Lumina/public evaluation using the current library and no new labels."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess

import luna_primary as shared
from analyze_export import load_secret, redactor
from prepare_corpus_study import EXFIL, public_rows, research_rows, history_rows


def prepare():
    os.umask(0o077)
    root = shared.ROOT
    directory = root / "output/shop_evaluation_20261025"
    if directory.exists():
        assert not any(directory.iterdir()), "Existing study must never be overwritten"
    directory.mkdir(parents=True, exist_ok=True)
    parent = root / "output/branch_replay_20261025/610c69ed_deepseek"
    prior_summary = shared.load(root / "data/results/lumina_deepseek_main_610c69e_20261025.json")
    settings = shared.load(parent / "settings.json")
    aliases = [r["alias"] for r in shared.load(root / "output/research_20261023/correspondencias_privadas.json")]
    real_secret = load_secret(root.parent / "promption_compe/.env.local")
    clean = redactor(real_secret, aliases)
    histories = history_rows()
    lumina = []
    for row in research_rows():
        if (row["participant_split_proposed"] != "test" or row["cohort"] != "post_reset"
                or row["annotation_confidence"] != "high" or row["operational_exclusion"]
                or row["injection_label_proposed"] not in (0, 1)):
            continue
        history = []
        for pair in histories[row["id"]]:
            history.append({"role": "user", "content": clean(pair["user"])})
            reply = clean(pair["assistant"])
            if re.search(r"(?i)promption|solicitud no clasificada|por seguridad, no se consult[oó]", reply):
                reply = "[Mensaje de control anterior omitido]"
            if reply:
                history.append({"role": "assistant", "content": reply})
        lumina.append(dict(id=row["id"], corpus="lumina", text=clean(row["prompt"]), history=history,
            label=row["injection_label_proposed"], language="es_or_mixed_unverified", group_id=row["family_id"],
            participant=row["participant_id"], split=row["participant_split_proposed"], context_required=row["context_required"],
            dataset="Lumina_competition", attack_type=row["intent_category"], annotation="provisional_silver_not_human_gold",
            exfil_target=bool(row["injection_label_proposed"] and (row["intent_category"] in {"secret_extraction", "system_prompt_extraction"}
                or EXFIL.search(row["prompt"])))))
    pools = {"lumina": [], "public": []}
    excluded = Counter()
    seen = set()
    for row in lumina + [r for r in public_rows() if r["split"] == "test"]:
        row = {**row, "text": clean(row["text"])}
        body = json.dumps({"text": row["text"], "history": row["history"]}, ensure_ascii=False)
        reason = ("privacy_redaction" if "REDACTAD" in body else "context_bound"
            if len(row["text"]) > 8000 or len(body) > 16000 or len(row["history"]) > 64 else None)
        if reason:
            excluded[row["corpus"] + ":" + reason] += 1
            continue
        key = hashlib.sha256((row["corpus"] + ":" + body).encode()).hexdigest()
        if key in seen:
            excluded[row["corpus"] + ":duplicate"] += 1
            continue
        seen.add(key)
        pools[row["corpus"]].append(row)
    rank = lambda row: hashlib.sha256(("shop-mixed-20261025:" + row["id"]).encode()).hexdigest()
    selected = []
    for corpus, pool in pools.items():
        target = 90 if corpus == "lumina" else 210
        for label in (0, 1):
            candidates = sorted([r for r in pool if r["label"] == label], key=lambda r: (r.get("split") != "test", rank(r)))
            assert len(candidates) >= target, (corpus, label, len(candidates))
            if corpus == "public":
                group = [r for r in candidates if r["language"] == "es"][:75]
            else:
                group = [r for r in candidates if r.get("context_required")][:50]
            ids = {r["id"] for r in group}
            group += [r for r in candidates if r["id"] not in ids][:target - len(group)]
            selected.extend(group)
    selected.sort(key=rank)
    assert len(selected) == 600 and len({r["id"] for r in selected}) == 600
    assert all(not shared.hits(json.dumps(row, ensure_ascii=False), real_secret) for row in selected)
    conditions = ["unprotected", "prompt_only", "promption"]
    plan = [{"id": f"{row['corpus']}_{row['id']}_{condition}", "case_id": row["id"], "condition": condition}
        for row in selected for condition in conditions]
    random.Random(20261025600).shuffle(plan)
    for name, data in [("settings.json", settings), ("cases_private.json", selected), ("plan.json", plan)]:
        shared.dump(directory / name, data)
    checkpoint = {"kind": "reserved", "call": "historical-checkpoint", "reserved_usd": prior_summary["total_cost_upper_usd"],
        "source": "Conservative cumulative checkpoint from previous aggregate, including earlier DeepSeek batches."}
    (directory / "prior_ledger.jsonl").write_text(json.dumps(checkpoint) + "\n")
    files = [str(p.relative_to(root)) for folder in ["promption", "packages/ai-sdk/src", "scripts/research"]
        for p in (root / folder).rglob("*") if p.is_file() and p.suffix in {".py", ".js", ".mjs"}
        and "node_modules" not in p.parts and "__pycache__" not in p.parts]
    files += ["config/config.yaml", "config/heuristics.yaml", "models/lightweight_classifier.pkl", "models/random_forest.pkl",
        "packages/ai-sdk/package.json", "pyproject.toml"]
    import promption
    protocol = dict(study="shop_mixed_three_conditions", provider="deepseek", library_version=promption.__version__,
        report_stem="shop_mixed_deepseek_20261025", commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        expected_model_release="DeepSeek-V4.1-Flash-1017", generation_model="deepseek-flash", scope_model="deepseek-flash", refusal_judge_model="deepseek-flash",
        allowed_response_models={"deepseek-flash": ["deepseek-flash", "DeepSeek-V4.1-Flash-1017", "deepseek-v4.1-flash-1017"]},
        budget_usd=5, prior_spent_upper_usd=prior_summary["total_cost_upper_usd"], prior_ledgers=[], prior_ledger_file="prior_ledger.jsonl",
        prior_ledger_sha256=shared.digest(directory / "prior_ledger.jsonl"), rates_usd_per_million={"deepseek-flash": {"input": .3, "output": 1.2}},
        max_api_calls=6000, max_output_tokens=1024, concurrency=12, min_request_interval_ms=0,
        request_timeout_ms=120000, episode_timeout_ms=300000, max_model_steps=3, max_tool_calls=2,
        conditions=conditions, cases=600, planned_episodes=1800, repetitions=1,
        source_counts={source: dict(Counter(str(r["label"]) for r in rows)) for source, rows in pools.items()},
        public_language_counts=dict(Counter(r["language"] for r in selected if r["corpus"] == "public")),
        public_dataset_counts=dict(Counter(r["dataset"] for r in selected if r["corpus"] == "public")),
        lumina_partition_counts=dict(Counter(r["split"] for r in selected if r["corpus"] == "lumina")),
        source_hashes={name: shared.digest(root / name) for name in ["data/processed/training_data.csv", "data/processed/split_manifest.json",
            "output/research_20261023/etiquetas_provisionales.jsonl", "output/research_20261023/contexto_y_trazabilidad_privado.jsonl"]},
        selection="600 cases: 180 Lumina (90 positive/90 negative) and 420 public (210 positive/210 negative). Deterministic selection independent of predictions. Previously exposed test partitions only; no training/validation cases. Public sampling reserves available Spanish cases up to75 per class, Lumina up to50 contextual cases per class. Lumina test availability after privacy exclusions has only94 eligible negatives; corpus-specific rates are reported separately. Not a new independent holdout.",
        privacy_exclusions=dict(excluded), detector_tuning=False, no_new_human_gold=True,
        execution_amendments=[], runtime_options={"thinking": {"type": "disabled"}, "maxRetries": 0},
        code_sha256={name: shared.digest(root / name) for name in sorted(set(files))},
        artifacts_sha256={name: shared.digest(directory / name) for name in ["settings.json", "cases_private.json", "plan.json", "prior_ledger.jsonl"]})
    shared.dump(directory / "protocol.json", protocol)
    for name in ["episodes", "requests", "api_responses", "artifacts"]:
        (directory / name).mkdir()
    for name in protocol["code_sha256"]:
        target = directory / "frozen_source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    print(json.dumps({"cases": 600, "episodes": 1800, "version": promption.__version__, "concurrency": 12,
        "prior_upper_usd": protocol["prior_spent_upper_usd"], "public_languages": protocol["public_language_counts"],
        "public_datasets": protocol["public_dataset_counts"]}))


if __name__ == "__main__":
    prepare()
