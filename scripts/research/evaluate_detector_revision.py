"""Paired offline input replay; never treat review as leakage or claim a model response was generated."""
import argparse
from collections import Counter
from dataclasses import replace
from functools import lru_cache
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare(path):
    sys.path.insert(0, str(ROOT))
    from prepare_corpus_study import public_rows, research_rows, history_rows
    history = history_rows()
    rows = [r for r in public_rows() if r["split"] == "test"]
    for row in research_rows():
        if row["cohort"] != "post_reset" or row["operational_exclusion"] or row["injection_label_proposed"] not in (0, 1):
            continue
        messages = [m for pair in history[row["id"]] for m in (
            {"role": "user", "content": pair["user"]},
            {"role": "assistant", "content": pair["assistant"]}) if m["content"]]
        rows.append(dict(id=row["id"], corpus="lumina", label=row["injection_label_proposed"],
            text=row["prompt"], history=messages, split=row["participant_split_proposed"],
            language="es_or_mixed", confidence=row["annotation_confidence"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("Frozen cases must not be overwritten")
    dump(path, rows)
    print(json.dumps({"cases": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))


def metrics(rows, key):
    valid = [r for r in rows if type(r.get(key)) is bool]
    counts = Counter(("TP" if r[key] else "FN") if r["label"] else ("FP" if r[key] else "TN") for r in valid)
    tp, fp, fn, tn = [counts[k] for k in ("TP", "FP", "FN", "TN")]
    ratio = lambda a, b: a / b if b else None
    return dict(n=len(rows), evaluated=len(valid), operational=len(rows) - len(valid),
        **{k: counts[k] for k in ("TP", "FP", "FN", "TN")},
        fpr=ratio(fp, fp + tn), fnr=ratio(fn, tp + fn), recall=ratio(tp, tp + fn),
        precision=ratio(tp, tp + fp), f1=ratio(2 * tp, 2 * tp + fp + fn),
        review=sum(r.get("route") == "review" for r in valid),
        attacks_review=sum(r["label"] == 1 and r.get("route") == "review" for r in valid),
        attacks_direct_allow=sum(r["label"] == 1 and r.get("route") == "allow" for r in valid))


def evaluate(source, output, library):
    sys.path.insert(0, str(library))
    import promption
    from promption.filter.ensemble_filter import EnsembleFilter
    from promption.conversation_guard import ConversationGuard
    from promption.guard import input_guard_decision
    from promption.training.artifacts import file_sha256
    from promption.utils.config import load_config
    logging.disable(logging.CRITICAL)
    output.mkdir(parents=True, exist_ok=False)
    rows = json.loads(source.read_text())
    source_hash = file_sha256(source)
    code_hashes = {str(p.relative_to(library)): file_sha256(p) for p in [
        library / "promption/evidence.py", library / "promption/filter/ensemble_filter.py",
        library / "promption/conversation_guard.py", library / "config/config.yaml", library / "config/heuristics.yaml"]}
    model_paths = [Path(load_config()["model"]["lightweight_classifier_path"])] + [
        Path(r["model_path"]) for r in load_config()["ensemble"].get("additional_classifiers", [])]
    model_hashes = {p.name: file_sha256(p) for p in model_paths}
    engine = EnsembleFilter()

    class CachedModel:
        is_loaded = True

        def __init__(self, model):
            self.model = model
            self.supported_origins = getattr(model, "supported_origins", {"user", "tool"})

        def is_trained(self):
            return self.model.is_trained()

        @lru_cache(maxsize=20000)
        def score(self, text):
            return self.model.analyze(text)

        def analyze(self, text):
            return replace(self.score(text))

    engine.ml = CachedModel(engine.ml)
    engine.additional_filters = tuple(CachedModel(model) for model in engine.additional_filters)
    guard = ConversationGuard(engine)
    results = []
    started = time.monotonic()
    for index, row in enumerate(rows, 1):
        current = {k: row[k] for k in ("id", "corpus", "split", "label", "language")}
        try:
            single = engine.analyze(row["text"], roles=["customer"])
            history = [*row["history"]]
            if not history or history[-1] != {"role": "user", "content": row["text"]}:
                history.append({"role": "user", "content": row["text"]})
            combined = guard.analyze(history, current_text=row["text"], roles=["customer"], isolate_history=True)
            result = {"blocked": single.blocked, "decision": single.decision,
                "requires_output_guard": single.requires_output_guard,
                "requires_scope_review": single.requires_scope_review,
                "input_risk_score": single.ml.probability if single.ml else None,
                "layers": {"conversation": combined.metadata()}}
            decision = input_guard_decision(row["text"], result, message_count=len(history),
                                            output_enabled=True, protection="balanced")
            if decision.status >= 500:
                raise RuntimeError(decision.reason)
            current.update(single_blocked=single.blocked, blocked=not decision.allowed,
                route="block" if not decision.allowed else "review" if decision.requires_output_guard else "allow",
                reason=decision.reason, history_isolated=combined.isolated_history,
                heuristic_rules=[r["name"] for r in single.heuristic.matched_rules],
                conversation_rules=combined.matched_rules)
        except Exception as error:
            current.update(error=type(error).__name__, route="operational")
        results.append(current)
        if index % 500 == 0:
            print(json.dumps({"processed": index, "total": len(rows), "seconds": round(time.monotonic() - started, 1)}), flush=True)
    slices = {"public_test": [r for r in results if r["corpus"] == "public"],
        "lumina_all_regression": [r for r in results if r["corpus"] == "lumina"],
        "lumina_participant_test": [r for r in results if r["corpus"] == "lumina" and r["split"] == "test"],
        "combined_regression": results}
    for language in sorted({r["language"] for r in results if r["corpus"] == "public"}):
        slices["public_test_" + language] = [r for r in results if r["corpus"] == "public" and r["language"] == language]
    summary = dict(library_version=promption.__version__, cases=len(rows), api_calls=0,
        source_sha256=source_hash, model_sha256=model_hashes[model_paths[0].name], model_sha256_by_artifact=model_hashes,
        code_sha256=code_hashes,
        elapsed_seconds=time.monotonic() - started,
        metrics={name: dict(ensemble=metrics(subset, "single_blocked"),
                            guarded_input=metrics(subset, "blocked")) for name, subset in slices.items()},
        limits=["Input-only replay: no generation, semantic scope model or measured exfiltration.",
            "FN means no local veto; review remains mandatory, not direct authorization.",
            "Source and provisional silver labels remain unchanged. Previously exposed regression data, not independent gold.",
            "All-Lumina regression includes training exposure. Participant test is reported separately.",
            "Deterministic scores cached; elapsed time is not a production latency measurement."])
    assert file_sha256(source) == source_hash
    assert all(file_sha256(library / name) == value for name, value in code_hashes.items())
    assert all(file_sha256(p) == model_hashes[p.name] for p in model_paths)
    dump(output / "predictions.json", results)
    dump(output / "summary.json", summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in {"code_sha256", "limits"}}, indent=2))


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "evaluate"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--library-root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source.resolve())
    else:
        evaluate(args.source.resolve(), args.output.resolve(), args.library_root.resolve())
