"""Replay a frozen diagnostic cohort locally, without sending chats to a provider."""
import argparse
from collections import Counter
import hashlib
import json
import logging
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from promption.filter.ensemble_filter import EnsembleFilter
from promption.utils.config import load_config


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(rows):
    result = Counter({name: 0 for name in ("TP", "TN", "FP", "FN")})
    for row in rows:
        if row["label"] not in (0, 1) or not isinstance(row["blocked"], bool):
            raise ValueError("Diagnostic comparisons require binary evaluated labels and decisions")
        result[("TP" if row["blocked"] else "FN") if row["label"] else
               ("FP" if row["blocked"] else "TN")] += 1
    return dict(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    baseline = json.loads(args.baseline.read_text())
    rows = {row["id"]: row for row in map(json.loads, args.annotations.read_text().splitlines())}
    eligible = {row["id"] for row in rows.values() if row["cohort"] == "post_reset"
                and row["annotation_confidence"] == "high" and not row["context_required"]
                and row["injection_label_proposed"] in (0, 1) and not row["operational_exclusion"]}
    if len({row["id"] for row in baseline}) != len(baseline) or eligible != {row["id"] for row in baseline}:
        raise ValueError("Baseline and current diagnostic cohort differ")
    after = []
    engine = EnsembleFilter()
    for previous in baseline:
        row = rows[previous["id"]]
        if row["injection_label_proposed"] != previous["label"]:
            raise ValueError("Diagnostic label changed after baseline capture")
        result = engine.analyze(row["prompt"])
        after.append({"id": row["id"], "label": previous["label"], "blocked": result.blocked,
                      "decision": result.decision, "rules": [rule["name"] for rule in result.heuristic.matched_rules]})
    files = [ROOT / name for name in ("config/heuristics.yaml", "promption/utils/text.py",
             "promption/filter/heuristic_filter.py", "promption/conversation_guard.py",
             "packages/ai-sdk/src/conversation.js")]
    model = Path(load_config()["model"]["lightweight_classifier_path"])
    report = {"method": "paired_local_single_message_diagnostic_replay",
              "labels": "provisional_silver_not_human_gold", "independent_test": False,
              "history_replayed": False, "provider_calls": 0, "model_retrained": False,
              "warning": "Diagnostic changes are not end-to-end attack success rates or publication-ready accuracy.",
              "n": len(baseline), "before": counts(baseline), "after": counts(after),
              "annotation_sha256": digest(args.annotations), "baseline_sha256": digest(args.baseline),
              "model_sha256": digest(model),
              "code_sha256": {str(path.relative_to(ROOT)): digest(path) for path in files},
              "changed": [{"id": a["id"], "label": a["label"], "before": b["blocked"], "after": a["blocked"]}
                          for b, a in zip(baseline, after) if b["blocked"] != a["blocked"]],
              "predictions": after}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({key: report[key] for key in ("n", "before", "after", "provider_calls")}, indent=2))


if __name__ == "__main__":
    main()
