"""Compare current history transitions against the preserved 1.3.2 wheel offline."""
import argparse
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import yaml

from promption.conversation_guard import ConversationGuard, ConversationLimitError
from promption.filter import EnsembleFilter
from promption.filter.heuristic_filter import HeuristicFilter
from promption.filter.ml_filter_lightweight import LightMLFilter
from promption.training.calibration import binary_metrics


def load_old(wheel, output):
    with zipfile.ZipFile(wheel) as archive:
        source = archive.read("promption/conversation_guard.py")
        config = yaml.safe_load(archive.read("promption/resources/heuristics.yaml"))
    module_path = output / "baseline_conversation_guard.py"
    module_path.write_bytes(source)
    spec = importlib.util.spec_from_file_location("promption._history_baseline_132", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.ConversationGuard, module.ConversationLimitError, config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--adapted-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    OldGuard, OldLimit, old_config = load_old(args.wheel, args.output)

    def engine(old=False):
        return EnsembleFilter(heuristic=HeuristicFilter(heuristics=old_config) if old else HeuristicFilter(),
            additional_filters=[LightMLFilter.from_artifact(args.adapted_model, threshold=.82)])

    old_engine, new_engine = engine(True), engine()
    before_guard, after_guard = OldGuard(old_engine), ConversationGuard(new_engine)
    source = json.loads(args.cases.read_text())
    cases = source["cases"]
    participants = {row["participant_id"] for row in cases if "participant_id" in row}
    labels = [json.loads(line) for line in (args.research / "etiquetas_provisionales.jsonl").read_text().splitlines()]
    history = {row["id"]: row["context"] for row in map(json.loads,
        (args.research / "contexto_y_trazabilidad_privado.jsonl").read_text().splitlines())}
    cohort = []
    for row in labels:
        if (row["participant_id"] not in participants or row["cohort"] != "post_reset"
                or row["annotation_confidence"] != "high" or row["policy_violation_proposed"] not in (0, 1)
                or row["operational_exclusion"]):
            continue
        messages = [message for pair in history[row["id"]] for message in (
            {"role": "user", "content": pair["user"]}, {"role": "assistant", "content": pair["assistant"]})
            if message["content"]]
        if "REDACTAD" in json.dumps({"text": row["prompt"], "messages": messages}):
            continue
        cohort.append({"id": row["id"], "text": row["prompt"], "messages": messages,
                       "cohort": "expanded_held_participants", "policy_label": row["policy_violation_proposed"]})
    predictions = []
    for row in cases + cohort:
        messages = row["messages"] + [{"role": "user", "content": row["text"]}]
        result = {"id": row["id"], "cohort": row["cohort"], "label": row["policy_label"]}
        for name, guard, detector in (("before", before_guard, old_engine), ("after", after_guard, new_engine)):
            try:
                decision = guard.analyze(messages)
                current = detector.analyze(row["text"])
                tool = bool(row.get("tool") and detector.analyze(json.dumps(row["tool"]["input"], ensure_ascii=False)).blocked)
                result[name] = {"blocked": current.blocked or decision.blocked or tool,
                    "current_blocked": current.blocked, "conversation_blocked": decision.blocked,
                    "requires_output_guard": current.requires_output_guard or decision.requires_output_guard,
                    "evaluation_mode": getattr(decision, "evaluation_mode", "cumulative"),
                    "rules": decision.matched_rules, "status": 200}
            except (ConversationLimitError, OldLimit):
                result[name] = {"status": 413}
        predictions.append(result)
    summary = {"provider_calls": 0, "labels": "provisional_silver_or_synthetic", "independent_test": False,
        "baseline_wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest(), "cohorts": {}}
    for name in sorted({row["cohort"] for row in predictions}):
        selected = [row for row in predictions if row["cohort"] == name]
        paired = [row for row in selected if row["before"]["status"] == row["after"]["status"] == 200]
        summary["cohorts"][name] = {"selected": len(selected), "paired": len(paired), "operational": len(selected)-len(paired),
            "metrics": {stage: binary_metrics([row["label"] for row in paired],
                                               [row[stage]["blocked"] for row in paired]) for stage in ("before", "after")},
            "changed": [{"id": row["id"], "label": row["label"], "before": row["before"]["blocked"],
                "after": row["after"]["blocked"], "requires_output_guard": row["after"]["requires_output_guard"]}
                for row in paired if row["before"]["blocked"] != row["after"]["blocked"]]}
    (args.output / "predictions.json").write_text(json.dumps(predictions, indent=2))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
