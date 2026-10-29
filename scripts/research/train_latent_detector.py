"""Validation-only search of a nonlinear local detector over compressed text features."""
import json
import logging
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline

from train_detector_revision import prepare, training_text, measure, dump
from promption.filter.heuristic_filter import HeuristicFilter
from promption.filter.text_scoring import score_texts
from promption.training.train_lightweight import build_vectorizer
from promption.training.artifacts import file_sha256


def run():
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    out = ROOT / "output/detector_revision_20261025/latent_v8"
    out.mkdir(exist_ok=False)
    rows, excluded = prepare()
    train = [r for r in rows if r["split"] == "train"]
    validation = {c: [r for r in rows if r["corpus"] == c and r["split"] == "val"] for c in ("public", "lumina")}
    hs = {c: [HeuristicFilter().analyze(r["text"]) for r in subset] for c, subset in validation.items()}
    baseline = joblib.load(ROOT / "models/lightweight_classifier.pkl")
    old = {c: score_texts(baseline["vectorizer"], baseline["classifier"], [training_text(r["text"]) for r in subset])
           for c, subset in validation.items()}
    caps = {c: min(measure(subset, old[c], t, hs[c])["fp"] for t in (.75, .85)) for c, subset in validation.items()}
    recall_floor = {c: measure(subset, old[c], .75, hs[c])["recall"] for c, subset in validation.items()}
    dump(out / "protocol.json", dict(selection="Validation-only: no increase in FPR at either baseline operating point or FNR at balanced input; maximize mean corpus recall.",
        components=[64, 128], leaves=[7, 15, 31], seed=42, api_calls=0, excluded=excluded,
        source_labels="Unchanged source/provisional silver labels, previously exposed regression.",
        baseline_sha256=file_sha256(ROOT / "models/lightweight_classifier.pkl"), caps=caps, recall_floor=recall_floor))
    vectorizer = build_vectorizer(24000)
    x = vectorizer.fit_transform([training_text(r["text"]) for r in train])
    val_x = {c: vectorizer.transform([training_text(r["text"]) for r in subset]) for c, subset in validation.items()}
    y = np.array([r["label"] for r in train])
    weights = np.array([.5 if r["corpus"] == "lumina" else 1. for r in train])
    candidates, best = [], None
    for size in (64, 128):
        svd = TruncatedSVD(n_components=size, n_iter=5, random_state=42)
        dense = svd.fit_transform(x)
        val_dense = {c: svd.transform(v) for c, v in val_x.items()}
        for leaves in (7, 15, 31):
            classifier = HistGradientBoostingClassifier(max_iter=300, max_leaf_nodes=leaves,
                learning_rate=.06, l2_regularization=2, random_state=42)
            classifier.fit(dense, y, sample_weight=weights)
            scores = {c: classifier.predict_proba(v)[:, 1] for c, v in val_dense.items()}
            feasible = []
            for threshold in np.arange(.25, .751, .01).round(2):
                metrics = {c: measure(subset, scores[c], threshold, hs[c]) for c, subset in validation.items()}
                if all(m["fp"] <= caps[c] and m["recall"] >= recall_floor[c] for c, m in metrics.items()):
                    rank = (float(np.mean([m["recall"] for m in metrics.values()])), -sum(m["fp"] for m in metrics.values()), -size, -leaves, float(threshold))
                    candidate = dict(components=size, leaves=leaves, threshold=float(threshold), metrics=metrics)
                    feasible.append(candidate)
                    if best is None or rank > best[0]:
                        best = (rank, candidate, svd, classifier)
            candidates.append(dict(components=size, leaves=leaves, feasible=feasible))
            dump(out / "validation.json", candidates)
            print(json.dumps(dict(components=size, leaves=leaves, feasible=len(feasible))), flush=True)
    if best is None:
        print("No feasible latent classifier; runtime unchanged.")
        return
    _, selected, svd, classifier = best
    dump(out / "selection_before_test.json", selected)
    artifact = dict(vectorizer=Pipeline([("features", vectorizer), ("projection", svd)]), classifier=classifier,
        model_type="tfidf_svd_hist_gradient_boosting", inference={"normalize": True}, recommended_threshold=selected["threshold"],
        annotation_status="PROVISIONAL_SILVER_NOT_HUMAN_GOLD")
    joblib.dump(artifact, out / "classifier.pkl")
    report = {}
    for c in validation:
        subset = [r for r in rows if r["split"] == "test" and r["corpus"] == c]
        heuristics = [HeuristicFilter().analyze(r["text"]) for r in subset]
        texts = [training_text(r["text"]) for r in subset]
        new = score_texts(artifact["vectorizer"], classifier, texts)
        old = score_texts(baseline["vectorizer"], baseline["classifier"], texts)
        report[c] = dict(old_ensemble=measure(subset, old, .85, heuristics),
            old_guarded_input=measure(subset, old, .75, heuristics), new=measure(subset, new, selected["threshold"], heuristics))
    dump(out / "results.json", dict(selected=selected, regression=report, model_sha256=file_sha256(out / "classifier.pkl")))
    print(json.dumps(dict(selected=selected, regression=report), indent=2))


if __name__ == "__main__":
    run()
