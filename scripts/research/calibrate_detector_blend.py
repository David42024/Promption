"""Select a frozen-model soft vote using validation only and retain every source label."""
from pathlib import Path
import json
import logging
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
from sklearn.ensemble import VotingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, LabelEncoder

from train_detector_revision import prepare, measure, training_text, dump
from promption.filter.heuristic_filter import HeuristicFilter
from promption.filter.text_scoring import score_texts
from promption.training.artifacts import file_sha256


def run():
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    directory = ROOT / "output/detector_revision_20261025/blend_v7"
    directory.mkdir(exist_ok=False)
    rows, _ = prepare()
    paths = [ROOT / "models/lightweight_classifier.pkl",
        ROOT / "output/detector_revision_20261025/trees_v4/classifier.pkl"]
    models = [joblib.load(p) for p in paths]
    validation = {c: [r for r in rows if r["corpus"] == c and r["split"] == "val"] for c in ("public", "lumina")}
    hs = {c: [HeuristicFilter().analyze(r["text"]) for r in subset] for c, subset in validation.items()}
    scores = {c: [score_texts(m["vectorizer"], m["classifier"], [training_text(r["text"]) for r in subset])
                  for m in models] for c, subset in validation.items()}
    baselines = {c: {str(t): measure(subset, scores[c][0], t, hs[c]) for t in (.75, .85)}
                 for c, subset in validation.items()}
    candidates = []
    for legacy_weight in [.1, .25, .5, .75]:
        for threshold in np.arange(.35, .751, .01).round(2):
            metrics = {c: measure(subset, legacy_weight * scores[c][0] + (1 - legacy_weight) * scores[c][1], threshold, hs[c])
                       for c, subset in validation.items()}
            feasible = all(m["fp"] <= min(baselines[c]["0.75"]["fp"], baselines[c]["0.85"]["fp"])
                           and m["fn"] <= baselines[c]["0.75"]["fn"] for c, m in metrics.items())
            candidates.append(dict(legacy_weight=legacy_weight, threshold=float(threshold), metrics=metrics,
                feasible=feasible, mean_recall=float(np.mean([m["recall"] for m in metrics.values()]))))
    dump(directory / "validation.json", dict(baselines=baselines, candidates=candidates,
        selection="Mean recall on validation; no corpus may increase FPR compared with either old operating point or FNR compared with the old balanced guard. No test data used.",
        model_sha256=[file_sha256(p) for p in paths]))
    feasible = [r for r in candidates if r["feasible"]]
    if not feasible:
        print("No feasible vote; runtime remains unchanged.")
        return
    selected = max(feasible, key=lambda r: (r["mean_recall"], -sum(m["fp"] for m in r["metrics"].values()), r["threshold"]))
    dump(directory / "selection_before_test.json", selected)
    pipelines = [(name, Pipeline([("features", m["vectorizer"]), ("classifier", m["classifier"])]))
                 for name, m in zip(("legacy", "adapted"), models)]
    weight = selected["legacy_weight"]
    classifier = VotingClassifier(pipelines, voting="soft", weights=[weight, 1 - weight])
    classifier.estimators_ = [p for _, p in pipelines]
    classifier.le_ = LabelEncoder().fit([0, 1])
    classifier.classes_ = np.array([0, 1])
    artifact = dict(vectorizer=FunctionTransformer(validate=False), classifier=classifier,
        model_type="tfidf_soft_vote", inference={"normalize": True},
        recommended_threshold=selected["threshold"], annotation_status="PROVISIONAL_SILVER_NOT_HUMAN_GOLD")
    joblib.dump(artifact, directory / "classifier.pkl")
    report = {}
    for c in validation:
        subset = [r for r in rows if r["split"] == "test" and r["corpus"] == c]
        heuristics = [HeuristicFilter().analyze(r["text"]) for r in subset]
        texts = [training_text(r["text"]) for r in subset]
        new = score_texts(artifact["vectorizer"], classifier, texts)
        old = score_texts(models[0]["vectorizer"], models[0]["classifier"], texts)
        report[c] = dict(old_ensemble=measure(subset, old, .85, heuristics),
            old_guarded_input=measure(subset, old, .75, heuristics),
            new=measure(subset, new, selected["threshold"], heuristics))
    dump(directory / "results.json", dict(selected=selected, regression=report,
        model_sha256=file_sha256(directory / "classifier.pkl"), api_calls=0,
        limits="Already exposed source/silver regression labels; no independent gold or exfiltration measurement."))
    print(json.dumps(dict(selected=selected, regression=report), indent=2))


if __name__ == "__main__":
    run()
