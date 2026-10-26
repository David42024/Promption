"""Replay only clarification policy on saved verdicts; never regenerate or estimate end-to-end FPR."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from promption.scope import _validated, needs_clarification


def replay(directory):
    cases = {c["id"]: c for c in json.loads((directory / "cases_private.json").read_text())}
    records = [json.loads(f.read_text()) for f in sorted((directory / "episodes").glob("*_promption.json"))]
    summaries = {}
    for profile in ("conversational", "balanced", "strict"):
        counts = Counter()
        for record in records:
            if record["status"] not in {"blocked", "clarified"} or record["reason"] not in {"ambiguous", "fixed_clarification"}:
                continue
            events = [e for e in record["events"] if e["stage"] == "context_scope"]
            if not events:
                continue
            last = events[-1]
            decision = _validated(last["decision"])
            clarify = needs_clarification(decision, tool=last.get("proposed_tool"), protection=profile)
            label = "source_positive" if cases[record["case_id"]]["label"] else "source_negative"
            counts["reviewed"] += 1
            counts["clarify" if clarify else "block"] += 1
            if clarify and record["status"] == "blocked":
                counts["blocked_to_clarification"] += 1
                counts[label + "_blocked_to_clarification"] += 1
            if not clarify and record["status"] == "clarified":
                counts["clarification_to_block"] += 1
        summaries[profile] = dict(counts)
    result = {"scope": "Saved semantic ambiguity verdicts only, not full pipeline or new model inference",
              "source": str(directory.relative_to(ROOT)), "distinct_protected_records": len(records),
              "profiles": summaries, "api_calls": 0,
              "limits": ["Uses the same already observed cases and automatic/silver labels.",
                         "A clarification neither authorizes generation/tools nor completes a task.",
                         "Strict input uncertainty and new model judgments are not replayed.",
                         "Does not establish new FPR/FNR, ASR, task completion or exfiltration rates."]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    replay(parser.parse_args().directory.resolve())
