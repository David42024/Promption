"""Join a fixed baseline with its authorized corrective replay, preserving both runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def load(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--corrected", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    original_bytes = (args.original / "cases_private.json").read_bytes()
    if original_bytes != (args.corrected / "cases_private.json").read_bytes():
        raise ValueError("Paired cases changed between stages")
    original = load(args.original / "api_summary.json")
    corrected = load(args.corrected / "api_summary.json")
    protocol = load(args.corrected / "protocol.json")
    additional = corrected["spent_upper_usd"] - protocol["prior_spent_upper_usd"]
    if corrected["calls"] > 50 or additional > .15 + 1e-6:
        raise ValueError("Corrective authorization bounds exceeded")
    before = [row for row in lines(args.original / "scope_results.jsonl") if row["profile"] == "legacy_scope"]
    after = lines(args.corrected / "scope_results.jsonl")
    if any(row["profile"] != "context_intent" for row in after):
        raise ValueError("Corrective stage must evaluate only the new context guard")
    joined = before + after
    if len({(row["id"], row["profile"]) for row in joined}) != len(joined):
        raise ValueError("Duplicate paired observations")
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    (args.output / "cases_private.json").write_bytes(original_bytes)
    (args.output / "scope_results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in joined))
    api = {"calls": original["calls"] + corrected["calls"], "corrective_calls": corrected["calls"],
           "spent_upper_usd": corrected["spent_upper_usd"], "corrective_spent_upper_usd": round(additional, 6),
           "budget_stopped": corrected["budget_stopped"], "stop_reason": corrected["stop_reason"],
           "decisions": len(joined), "external_tools_executed": 0}
    (args.output / "api_summary.json").write_text(json.dumps(api, indent=2))
    manifest = {"baseline_source": str(args.original), "context_source": str(args.corrected),
                "same_cases_sha256": hashlib.sha256(original_bytes).hexdigest(),
                "legacy_decisions_reused_without_new_calls": len(before), "new_context_decisions": len(after),
                "same_silver_judge_family": True, "post_diagnostic_fix_not_independent_test": True}
    (args.output / "paired_manifest.json").write_text(json.dumps(manifest, indent=2))
    subprocess.run([sys.executable, str(Path(__file__).with_name("summarize_context_eval.py")),
                    str(args.output)], check=True, stdout=subprocess.DEVNULL)
    summary = load(args.output / "summary.json")
    print(json.dumps({"api": api, "cohorts": {key: {field: value[field] for field in (
        "selected", "paired_evaluated", "excluded_operational_or_incomplete", "metrics", "semantic_paired_comparison")}
        for key, value in summary["cohorts"].items()}}, indent=2))


if __name__ == "__main__":
    main()
