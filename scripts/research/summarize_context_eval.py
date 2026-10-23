"""Summarize a frozen paired evaluation while separating policy, attacks and outages."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path


def metrics(labels, predictions):
    counts = Counter({key: 0 for key in ("tp", "fp", "fn", "tn")})
    for label, prediction in zip(labels, predictions):
        counts[("tp" if prediction else "fn") if label else ("fp" if prediction else "tn")] += 1
    tp, fp, fn, tn = (counts[key] for key in ("tp", "fp", "fn", "tn"))
    return {**counts, "n": len(labels), "recall": tp / (tp + fn) if tp + fn else None,
            "fpr": fp / (fp + tn) if fp + tn else None,
            "precision": tp / (tp + fp) if tp + fp else None}


def exact_mcnemar(before, after, labels):
    corrected = sum(a != bool(y) and b == bool(y) for a, b, y in zip(before, after, labels))
    regressed = sum(a == bool(y) and b != bool(y) for a, b, y in zip(before, after, labels))
    n = corrected + regressed
    p = min(1, 2 * sum(math.comb(n, k) for k in range(min(corrected, regressed) + 1)) / 2 ** n) if n else 1
    return {"corrected": corrected, "regressed": regressed, "exact_p_two_sided_unadjusted": p,
            "inferential_use": False, "caveat": "Repeated prompts share participants; no clustering adjustment or gold labels"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    folder = args.folder
    cases = json.loads((folder / "cases_private.json").read_text())["cases"]
    rows = [json.loads(line) for line in (folder / "scope_results.jsonl").read_text().splitlines()]
    predictions = {(row["id"], row["profile"]): row["decision"] for row in rows}
    result = {"api": json.loads((folder / "api_summary.json").read_text()), "cohorts": {},
              "positive_definition": "policy violation, not necessarily an injection attack",
              "accuracy_labels": "provisional_silver_except_predeclared_synthetic_controls",
              "end_to_end_secret_leakage_measured": False}
    for cohort in sorted({row["cohort"] for row in cases}):
        selected = [row for row in cases if row["cohort"] == cohort]
        paired = [row for row in selected if all((row["id"], profile) in predictions
                  and predictions[row["id"], profile]["status"] in (200, 403)
                  for profile in ("legacy_scope", "context_intent"))]
        labels = [row["policy_label"] for row in paired]
        methods = {}
        for profile in ("legacy_scope", "context_intent"):
            methods[profile] = [not predictions[row["id"], profile]["allowed"] for row in paired]
        for profile in ("baseline", "extended"):
            methods[profile + "_local"] = [row[profile + "_local"]["blocked"] for row in paired]
            for semantic in ("legacy_scope", "context_intent"):
                methods[profile + "+" + semantic] = [row[profile + "_local"]["blocked"] or semantic_block
                                                    for row, semantic_block in zip(paired, methods[semantic])]
        changes = [{"id": row["id"], "label": row["policy_label"],
                    "legacy_denied": methods["legacy_scope"][i], "context_denied": methods["context_intent"][i],
                    "base_history_veto": row["baseline_local"]["conversation_blocked"],
                    "context_reason": predictions[row["id"], "context_intent"]["reason"]}
                   for i, row in enumerate(paired) if methods["legacy_scope"][i] != methods["context_intent"][i]]
        result["cohorts"][cohort] = {"selected": len(selected), "paired_evaluated": len(paired),
            "excluded_operational_or_incomplete": len(selected) - len(paired),
            "metrics": {name: metrics(labels, values) for name, values in methods.items()},
            "per_profile_all_available": {profile: {
                "semantic_only": metrics(
                    [row["policy_label"] for row in selected if (row["id"], profile) in predictions
                     and predictions[row["id"], profile]["status"] in (200, 403)],
                    [not predictions[row["id"], profile]["allowed"] for row in selected if (row["id"], profile) in predictions
                     and predictions[row["id"], profile]["status"] in (200, 403)]),
                "operational_failures_by_label": dict(Counter(row["policy_label"] for row in selected
                    if (row["id"], profile) in predictions and predictions[row["id"], profile]["status"] not in (200, 403))),
                "effective_denials_including_operational": metrics(
                    [row["policy_label"] for row in selected if (row["id"], profile) in predictions],
                    [not predictions[row["id"], profile]["allowed"] for row in selected if (row["id"], profile) in predictions]),
            } for profile in ("legacy_scope", "context_intent")},
            "semantic_paired_comparison": exact_mcnemar(methods["legacy_scope"], methods["context_intent"], labels),
            "semantic_changes": changes,
            "reasons": {profile: dict(Counter(predictions[row["id"], profile]["reason"] for row in selected
                                 if (row["id"], profile) in predictions)) for profile in ("legacy_scope", "context_intent")},
            "context_strata": {str(context): {profile: metrics(
                [row["policy_label"] for row in paired if row["context_required"] == context],
                [value for row, value in zip(paired, values) if row["context_required"] == context])
                for profile, values in methods.items()} for context in (False, True)}}
    (folder / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
