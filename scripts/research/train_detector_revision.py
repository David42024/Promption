"""Adapt the local detector on training data and select only on frozen validation splits."""
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

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.svm import LinearSVC
from sklearn.ensemble import ExtraTreesClassifier

from analyze_export import load_secret, redactor
from guardrail_strategies import near_index, overlaps
from prepare_corpus_study import public_rows, research_rows
from promption.evidence import interpret_input
from promption.filter.heuristic_filter import HeuristicFilter
from promption.filter.text_scoring import score_texts
from promption.training.artifacts import file_sha256
from promption.training.calibration import binary_metrics
from promption.training.train_lightweight import build_vectorizer
from promption.utils.config import load_config
from promption.utils.text import normalize_content


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def training_text(text):
    return normalize_content(interpret_input(text).instruction_text)


def prepare():
    public = public_rows()
    annotation = research_rows()
    aliases = [r["alias"] for r in json.loads((ROOT / "output/research_20261023/correspondencias_privadas.json").read_text())]
    secret = load_secret(ROOT.parent / "promption_compe/.env.local")
    clean = redactor(secret, aliases)
    lumina, excluded = [], Counter()
    heldout_public = near_index([r["text"] for r in public if r["split"] in {"val", "test"}])
    train_public = near_index([r["text"] for r in public if r["split"] == "train"])
    for row in annotation:
        if row["training_candidate_exclusion"]:
            excluded[row["training_candidate_exclusion"]] += 1
            continue
        text = clean(row["prompt"])
        if "REDACTAD" in text or len(text) > 8000:
            excluded["privacy_or_length"] += 1
            continue
        split = row["split_proposed"]
        if overlaps(text, heldout_public if split == "train" else train_public):
            excluded["cross_corpus_overlap"] += 1
            continue
        lumina.append(dict(id=row["id"], corpus="lumina", text=text, label=row["injection_label_proposed"],
            split={"validation": "val"}.get(split, split), group_id=row["family_id"],
            participant=row["participant_id"], language="es_or_mixed", dataset="Lumina_silver"))
    for left in ("train", "val", "test"):
        for right in ("train", "val", "test"):
            if left >= right:
                continue
            for key in ("group_id", "participant"):
                assert not ({r[key] for r in lumina if r["split"] == left}
                            & {r[key] for r in lumina if r["split"] == right})
    excluded["public_unassigned"] = sum(r["split"] == "unassigned" for r in public)
    rows = [r for r in public if r["split"] != "unassigned"] + lumina
    assert all(r["split"] in {"train", "val", "test", "external"} for r in rows)
    return rows, dict(excluded)


def measure(rows, scores, threshold, heuristics):
    blocked = np.asarray([h.blocked for h in heuristics]) | (
        np.asarray([h.signal != "benign" for h in heuristics]) & (scores >= threshold))
    return binary_metrics([r["label"] for r in rows], blocked)


def run(output, calibrated=False, trees=False, quarantine_conflicts=False, min_leaf=1):
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    output.mkdir(parents=True, exist_ok=False)
    rows, excluded = prepare()
    conf = load_config()
    baseline_path = Path(conf["model"]["lightweight_classifier_path"])
    baseline = joblib.load(baseline_path)
    heuristic = HeuristicFilter()
    train = [r for r in rows if r["split"] == "train"]
    conflicts = [r for r in train if (r["label"] == 0 and heuristic.analyze(r["text"]).blocked)
                 or (r["label"] == 1 and heuristic.analyze(r["text"]).signal == "benign")]
    if quarantine_conflicts:
        conflicts_ids = {r["id"] for r in conflicts}
        train = [r for r in train if r["id"] not in conflicts_ids]
    validation = {name: [r for r in rows if r["split"] == "val" and r["corpus"] == name]
                  for name in ("public", "lumina")}
    heuristic_val = {name: [heuristic.analyze(r["text"]) for r in subset] for name, subset in validation.items()}
    baseline_val = {name: measure(subset, score_texts(baseline["vectorizer"], baseline["classifier"],
        [interpret_input(r["text"]).instruction_text for r in subset], inference=baseline.get("inference")),
        .75, heuristic_val[name]) for name, subset in validation.items()}
    baseline_ensemble = {name: measure(subset, score_texts(baseline["vectorizer"], baseline["classifier"],
        [interpret_input(r["text"]).instruction_text for r in subset], inference=baseline.get("inference")),
        .85, heuristic_val[name]) for name, subset in validation.items()}
    protocol = dict(training_only=True, threshold_selection="validation_only", labels="source_and_provisional_silver_unchanged",
        inference={"normalize": True}, c_grid=[.5, 2., 8.], lumina_weight_grid=[.5, 1.5],
        thresholds=np.arange(.25, .951, .01).round(2).tolist(), baseline_effective_threshold=.75,
        calibrated=calibrated, trees=trees,
        min_samples_leaf=min_leaf,
        quarantine_training_conflicts=quarantine_conflicts,
        training_conflicts={"n": len(conflicts), "by_corpus_label": dict(Counter(f"{r['corpus']}:{r['label']}" for r in conflicts)),
            "sha256": hashlib.sha256(json.dumps(sorted(r["id"] for r in conflicts)).encode()).hexdigest(),
            "meaning": "Conservative training quarantine, not a relabeling. Every validation/test label and row remains unchanged."},
        selection="Maximize mean corpus recall subject to no increase in either validation FPR or FNR and lower total FP. Tie: fewer FP, smaller C, smaller domain weight, higher threshold.",
        excluded=excluded, counts=dict(Counter(f"{r['corpus']}:{r['split']}:{r['label']}" for r in rows)),
        baseline_model_sha256=file_sha256(baseline_path),
        source_sha256={str(p.relative_to(ROOT)): file_sha256(p) for p in [
            ROOT / "data/processed/training_data.csv", ROOT / "data/processed/split_manifest.json",
            ROOT / "output/research_20261023/etiquetas_provisionales.jsonl",
            ROOT / "promption/evidence.py", ROOT / "config/heuristics.yaml", Path(__file__)]},
        api_calls=0, test_status="Previously exposed regression partitions. Not fitted or used for selection in this run.")
    dump(output / "protocol.json", protocol)
    dump(output / "baseline_validation.json", baseline_val)
    dump(output / "baseline_ensemble_validation.json", baseline_ensemble)
    frame = pd.DataFrame({"prompt": [training_text(r["text"]) for r in train], "label": [r["label"] for r in train]})
    groups = [r.get("participant", r["group_id"]) for r in train]
    folds = list(StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=42).split(frame, frame["label"], groups))
    candidates = []
    best = None
    vectorizer = build_vectorizer(24000)
    features = vectorizer.fit_transform(frame["prompt"])
    y = frame["label"].to_numpy()
    transformed = {name: vectorizer.transform([training_text(r["text"]) for r in subset])
                   for name, subset in validation.items()}
    for weight in protocol["lumina_weight_grid"]:
        weights = np.asarray([weight if r["corpus"] == "lumina" else 1. for r in train])
        for c in protocol["c_grid"]:
            classifier = (ExtraTreesClassifier(n_estimators=240, max_depth=int(c * 8 + 16),
                min_samples_leaf=min_leaf, max_features="sqrt", class_weight="balanced", n_jobs=2, random_state=42) if trees else
                CalibratedClassifierCV(LinearSVC(C=c, class_weight="balanced", max_iter=5000,
                random_state=42), method="sigmoid", cv=folds) if calibrated else
                LogisticRegression(C=c, class_weight="balanced", max_iter=1500, random_state=42))
            classifier.fit(features, y, sample_weight=weights)
            scores = {name: classifier.predict_proba(x)[:, list(classifier.classes_).index(1)]
                      for name, x in transformed.items()}
            feasible = []
            observations = []
            for threshold in protocol["thresholds"]:
                metrics = {name: measure(subset, scores[name], threshold, heuristic_val[name])
                           for name, subset in validation.items()}
                observations.append(dict(threshold=threshold, metrics=metrics))
                if (all(metrics[name]["fp"] <= min(baseline_val[name]["fp"], baseline_ensemble[name]["fp"])
                        and metrics[name]["fn"] <= baseline_val[name]["fn"] for name in metrics)
                        and sum(m["fp"] for m in metrics.values()) < sum(m["fp"] for m in baseline_val.values())):
                    mean_recall = float(np.mean([m["recall"] for m in metrics.values()]))
                    rank = (mean_recall, -sum(m["fp"] for m in metrics.values()), -c, -weight, threshold)
                    feasible.append(dict(threshold=threshold, metrics=metrics, mean_recall=mean_recall))
                    if best is None or rank > best[0]:
                        best = (rank, dict(C=c, weight=weight, threshold=threshold, validation=metrics), vectorizer, classifier)
            candidates.append(dict(C=c, weight=weight, feasible=feasible, observations=observations))
            dump(output / "candidates.json", candidates)
            print(json.dumps({"C": c, "weight": weight, "feasible": len(feasible),
                              "best_mean_recall": max((a["mean_recall"] for a in feasible), default=None)}), flush=True)
    dump(output / "candidates.json", candidates)
    if best is None:
        raise ValueError("No candidate reduces validation false positives; runtime unchanged")
    _, selected, vectorizer, classifier = best
    dump(output / "selection_before_test.json", selected)
    artifact = dict(vectorizer=vectorizer, classifier=classifier, model_type="tfidf_extra_trees" if trees else
        "tfidf_calibrated_svm" if calibrated else "tfidf_logistic_regression",
        feature_mode="word_and_char_ngrams", max_features=24000, inference={"normalize": True},
        recommended_threshold=selected["threshold"], annotation_status="PROVISIONAL_SILVER_NOT_HUMAN_GOLD")
    joblib.dump(artifact, output / "classifier.pkl")
    evaluation = {}
    for corpus in ("public", "lumina"):
        subset = [r for r in rows if r["split"] == "test" and r["corpus"] == corpus]
        heuristics = [heuristic.analyze(r["text"]) for r in subset]
        texts = [interpret_input(r["text"]).instruction_text for r in subset]
        old = score_texts(baseline["vectorizer"], baseline["classifier"], texts, inference=baseline.get("inference"))
        new = score_texts(vectorizer, classifier, texts, inference=artifact["inference"])
        evaluation[corpus] = dict(baseline=measure(subset, old, .75, heuristics),
            candidate=measure(subset, new, selected["threshold"], heuristics),
            by_dataset={name: dict(baseline=measure([r for r in subset if r["dataset"] == name],
                old[[r["dataset"] == name for r in subset]], .75, [h for h,r in zip(heuristics,subset) if r["dataset"] == name]),
                candidate=measure([r for r in subset if r["dataset"] == name],new[[r["dataset"] == name for r in subset]],
                selected["threshold"],[h for h,r in zip(heuristics,subset) if r["dataset"] == name])) for name in sorted({r["dataset"] for r in subset})})
    result = dict(protocol=protocol, selected=selected, heldout=evaluation, model_sha256=file_sha256(output / "classifier.pkl"))
    assert all(file_sha256(ROOT / name) == value for name, value in protocol["source_sha256"].items())
    dump(output / "results.json", result)
    print(json.dumps({"selected": selected, "heldout": evaluation}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibrated", action="store_true")
    parser.add_argument("--trees", action="store_true")
    parser.add_argument("--quarantine-training-conflicts", action="store_true")
    parser.add_argument("--min-leaf", type=int, default=1)
    args = parser.parse_args()
    run(args.output.resolve(), calibrated=args.calibrated, trees=args.trees,
        quarantine_conflicts=args.quarantine_training_conflicts, min_leaf=args.min_leaf)
