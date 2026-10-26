"""Replay annotated Lumina turns through current local guards without external inference."""
import argparse
from collections import Counter
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evaluate_local_profiles import PROFILES, digest, metrics
from prepare_corpus_study import CachedEnsemble, history_rows, research_rows


def run(output):
    import promption
    from promption.conversation_guard import ConversationGuard
    from promption.guard import input_guard_decision
    from promption.utils.config import load_config

    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    output.mkdir(parents=True, exist_ok=False)
    annotations = research_rows()
    histories = history_rows()
    eligible = []
    exclusions = Counter()
    for row in annotations:
        reason = ("before_reset" if row["cohort"] != "post_reset" else
                  "operational_exclusion" if row["operational_exclusion"] else
                  "without_binary_label" if row["injection_label_proposed"] not in (0, 1) else None)
        if reason:
            exclusions[reason] += 1
        else:
            eligible.append(row)
    assert len({row["id"] for row in eligible}) == len(eligible)
    source_files = ["output/research_20261023/etiquetas_provisionales.jsonl",
                    "output/research_20261023/contexto_y_trazabilidad_privado.jsonl"]
    code_files = ["promption/guard.py", "promption/profiles.py", "promption/conversation_guard.py",
                  "promption/filter/ensemble_filter.py", "promption/filter/heuristic_filter.py",
                  "promption/filter/ml_filter.py", "promption/evidence.py", "promption/encoded_evidence.py",
                  "promption/assessments.py", "config/config.yaml", "config/heuristics.yaml",
                  "scripts/research/evaluate_lumina_profiles.py", "scripts/research/evaluate_local_profiles.py",
                  "scripts/research/prepare_corpus_study.py"]
    hashes = {name: digest(ROOT / name) for name in source_files + code_files}
    model = Path(load_config()["model"]["lightweight_classifier_path"])
    model_hash = digest(model)
    engine = CachedEnsemble()
    conversation = ConversationGuard(engine)
    predictions = []
    started = time.monotonic()
    for index, row in enumerate(eligible, 1):
        history = [message for pair in histories[row["id"]] for message in (
            {"role": "user", "content": pair["user"]},
            {"role": "assistant", "content": pair["assistant"]}) if message["content"]]
        if not history or history[-1] != {"role": "user", "content": row["prompt"]}:
            history.append({"role": "user", "content": row["prompt"]})
        identity = {"id": row["id"], "label": row["injection_label_proposed"],
                    "split": row["participant_split_proposed"], "confidence": row["annotation_confidence"],
                    "duplicate": bool(row["duplicate_of"]), "with_history": len(history) > 1,
                    "episode_sha256": hashlib.sha256(json.dumps(history, ensure_ascii=False,
                        sort_keys=True).encode()).hexdigest()}
        try:
            single = engine.analyze(row["prompt"], roles=["customer"])
            combined = conversation.analyze(history, roles=["customer"], current_text=row["prompt"],
                                            isolate_history=True)
            result = {"blocked": single.blocked, "decision": single.decision,
                      "requires_output_guard": single.requires_output_guard,
                      "requires_scope_review": getattr(single, "requires_scope_review", False),
                      "input_risk_score": single.ml.probability if single.ml else None,
                      "layers": {"conversation": combined.metadata()}}
            for profile in PROFILES:
                decision = input_guard_decision(row["prompt"], result, message_count=len(history),
                                                output_enabled=True, protection=profile)
                if decision.status >= 500:
                    predictions.append({**identity, "profile": profile, "route": "operational",
                                        "error": decision.reason})
                    continue
                predictions.append({**identity, "profile": profile, "blocked": not decision.allowed,
                    "route": "block" if not decision.allowed else
                             "review" if decision.requires_output_guard else "allow",
                    "reason": decision.reason,
                    "requires_scope_review": getattr(decision, "requires_scope_review", False),
                    "history_isolated": combined.isolated_history,
                    "single_veto": single.blocked, "history_veto": combined.blocked,
                    "heuristic_rules": [rule["name"] for rule in single.heuristic.matched_rules],
                    "conversation_rules": combined.matched_rules})
        except Exception as error:
            predictions.extend({**identity, "profile": profile, "route": "operational",
                                "error": type(error).__name__} for profile in PROFILES)
        if index % 100 == 0 or index == len(eligible):
            print(json.dumps({"processed": index, "total": len(eligible),
                              "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)
    def summarize(rows):
        valid = [row for row in rows if row["route"] != "operational"]
        unique = {row["episode_sha256"]: row for row in valid}
        return {"planned": len(rows), "operational": len(rows) - len(valid),
                **metrics(valid), "unique_episode_sensitivity": metrics(list(unique.values()))}

    summary = {"study": "lumina_full_offline_profiles", "library_version": promption.__version__,
        "annotation_records": len(annotations), "eligible_turns": len(eligible),
        "executions": len(predictions), "exclusions": dict(exclusions),
        "source_and_code_sha256": hashes, "model_sha256": model_hash,
        "elapsed_seconds": time.monotonic() - started, "api_calls": 0, "cost_usd": 0,
        "label_counts": dict(Counter(row["injection_label_proposed"] for row in eligible)),
        "confidence_counts": dict(Counter(row["annotation_confidence"] for row in eligible)),
        "duplicate_markers": sum(bool(row["duplicate_of"]) for row in eligible),
        "profiles": {profile: {name: summarize([row for row in predictions if row["profile"] == profile
                          and predicate(row)]) for name, predicate in {
            "all_regression": lambda row: True,
            "participant_test": lambda row: row["split"] == "test",
            "high_confidence_test": lambda row: row["split"] == "test" and row["confidence"] == "high",
            "without_duplicate_markers": lambda row: not row["duplicate"]}.items()} for profile in PROFILES},
        "limits": ["Labels are provisional silver annotations, not adjudicated human gold.",
            "All-regression results include training/development exposure. Participant-test results are separate but previously exposed to diagnostics.",
            "FN means no local input veto. Review requires semantic evaluation and Output Guard; it is not permission to disclose.",
            "No generation, semantic LLM evaluation, live tools or observed exfiltration in this offline replay.",
            "Historical user/assistant context is replayed as stored. These context files do not constitute a replay of every historical tool result.",
            "Counts refer to annotation records, not the initial reported competition prompt counter.",
            "Unique-episode sensitivity deduplicates exact current input and history; primary results retain all eligible turns.",
            "Cached deterministic results are reused across profiles; timings are not production latency benchmarks."]}
    assert all(digest(ROOT / name) == value for name, value in hashes.items())
    assert digest(model) == model_hash
    (output / "predictions.json").write_text(json.dumps(predictions, ensure_ascii=False, indent=2))
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({"complete": True, "eligible_turns": len(eligible), "executions": len(predictions),
                      "profiles": summary["profiles"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve())
