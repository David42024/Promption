"""Paired, offline detector triage on the frozen Lumina/public regression sample."""
import argparse
from collections import Counter
import hashlib
import json
import logging
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ("conversational", "balanced", "strict")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(rows):
    counts = Counter(("TP" if r["blocked"] else "FN") if r["label"] else
                     ("FP" if r["blocked"] else "TN") for r in rows)
    positive = sum(r["label"] == 1 for r in rows)
    negative = sum(r["label"] == 0 for r in rows)
    return {"n": len(rows), **{key: counts[key] for key in ("TP", "FP", "FN", "TN")},
            "fpr": counts["FP"] / negative if negative else None,
            "fnr_veto": counts["FN"] / positive if positive else None,
            "routes": dict(Counter(r["route"] for r in rows)),
            "attacks_direct_allow": sum(r["label"] == 1 and r["route"] == "allow" for r in rows),
            "attacks_review": sum(r["label"] == 1 and r["route"] == "review" for r in rows),
            "benign_review": sum(r["label"] == 0 and r["route"] == "review" for r in rows),
            "scope_review_required": sum(r["requires_scope_review"] for r in rows)}


def run(source, output, library_root):
    sys.path.insert(0, str(library_root))
    import promption
    from promption.conversation_guard import ConversationGuard
    from promption.filter.ensemble_filter import EnsembleFilter
    from promption.guard import input_guard_decision
    from promption.profiles import resolve_protection
    from promption.scope import _validated, needs_clarification
    from promption.utils.config import load_config

    logging.disable(logging.CRITICAL)
    cases = json.loads(source.read_text())
    assert len(cases) == len({case["id"] for case in cases})
    assert all(type(case["label"]) is int and case["label"] in (0, 1) for case in cases)
    assert Counter((c["corpus"], c["label"]) for c in cases) == {
        (corpus, label): 60 for corpus in ("lumina", "public") for label in (0, 1)}
    engine = EnsembleFilter()
    conversation = ConversationGuard(engine)
    predictions = []
    started = time.monotonic()
    for case in cases:
        history = [*case["history"], {"role": "user", "content": case["text"]}]
        for profile in PROFILES:
            single = engine.analyze(case["text"], roles=["customer"])
            combined = conversation.analyze(history, roles=["customer"], current_text=case["text"],
                                            isolate_history=True)
            result = {"blocked": single.blocked, "decision": single.decision,
                      "requires_output_guard": single.requires_output_guard,
                      "requires_scope_review": getattr(single, "requires_scope_review", False),
                      "input_risk_score": single.ml.probability if single.ml else None,
                      "layers": {"conversation": combined.metadata()}}
            decision = input_guard_decision(case["text"], result, message_count=len(history),
                                            output_enabled=True, protection=profile)
            assert decision.status < 500, (case["id"], profile, decision.reason)
            predictions.append({"id": case["id"], "profile": profile, "corpus": case["corpus"],
                "language": case["language"], "label": case["label"],
                "blocked": not decision.allowed, "route": "block" if not decision.allowed else
                "review" if decision.requires_output_guard else "allow",
                "reason": decision.reason, "requires_scope_review": getattr(decision, "requires_scope_review", False),
                "conclusive_veto": single.blocked or combined.blocked,
                "heuristic_rules": [r["name"] for r in single.heuristic.matched_rules],
                "conversation_rules": combined.matched_rules})

    replay = {}
    for profile in PROFILES:
        counts = Counter()
        for case in cases:
            file = source.parent / "episodes" / f"{case['corpus']}_{case['id']}_promption.json"
            if not file.exists():
                counts["missing_record"] += 1
                continue
            record = json.loads(file.read_text())
            events = [event for event in record["events"] if event["stage"] == "context_scope"]
            if not events:
                counts["no_saved_verdict"] += 1
                continue
            event = events[0]
            decision = _validated(event["decision"])
            action = "allow" if decision.allowed else "clarify" if needs_clarification(
                decision, tool=event.get("proposed_tool"), protection=profile) else "block"
            counts["saved_verdicts"] += 1
            counts[action] += 1
        replay[profile] = dict(counts)

    source_names = ["promption/guard.py", "promption/profiles.py", "promption/scope.py",
                    "promption/evidence.py", "promption/assessments.py", "promption/conversation_guard.py",
                    "promption/filter/ensemble_filter.py", "promption/filter/heuristic_filter.py",
                    "config/config.yaml", "config/heuristics.yaml"]
    model = Path(load_config()["model"]["lightweight_classifier_path"])
    summary = {"library_version": promption.__version__, "study": "offline_profile_triage",
        "cases": len(cases), "executions": len(predictions), "elapsed_seconds": time.monotonic() - started,
        "api_calls": 0, "cost_usd": 0, "source_sha256": digest(source), "model_sha256": digest(model),
        "source_sha256_by_file": {name: digest(library_root / name) for name in source_names if (library_root / name).exists()},
        "runner_sha256": digest(Path(__file__)),
        "protection": {name: resolve_protection(name).to_dict() for name in PROFILES},
        "counts": {"corpus_label": {f"{corpus}:{label}": n for (corpus, label), n in
            Counter((c["corpus"], c["label"]) for c in cases).items()},
            "languages": dict(Counter(c["language"] for c in cases)),
            "with_history": sum(bool(c["history"]) for c in cases)},
        "profiles": {name: {"pooled": metrics([r for r in predictions if r["profile"] == name]),
            "by_corpus": {corpus: metrics([r for r in predictions if r["profile"] == name and r["corpus"] == corpus])
                          for corpus in ("lumina", "public")},
            "by_language": {language: metrics([r for r in predictions if r["profile"] == name and r["language"] == language])
                            for language in sorted({c["language"] for c in cases})}} for name in PROFILES},
        "historical_scope_replay": {"profiles": replay, "note":
            "First recorded scope verdict per case, from the prior 1.4.0 API study. Separate policy replay, not new semantic inference or a combined pipeline result."},
        "limits": ["Already exposed 240-case stratified regression sample; provisional source/silver labels, no independent gold.",
            "Each profile runs the actual local heuristic, trained ML, conversation guard and input policy, with identical inputs.",
            "No LLM, newly evaluated semantic intent/scope, generation, tools or exfiltration attempts.",
            "Review is not permission to generate. Required semantic review and Output Guard must still run; absent required scope evaluator fails closed.",
            "FN here means no input veto, not successful injection; report review and direct allow separately.",
            "Full-episode indirect-injection labels may describe later tool content absent from this input-only evaluation.",
            "Language for Lumina is es_or_mixed_unverified. Do not describe all 240 cases as confirmed Spanish/English.",
            "Scores are uncalibrated detection scores, not risk probabilities."]}
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    (output / "predictions.json").write_text(json.dumps(predictions, ensure_ascii=False, indent=2))
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "output/corpus_repeat_140_20261024/cases_private.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--library-root", type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.source.resolve(), args.output.resolve(), args.library_root.resolve())
