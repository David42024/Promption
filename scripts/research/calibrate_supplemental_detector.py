"""Calibrate a single-turn supplemental veto without fitting or selecting on participant test data."""
import json
import logging
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np

from prepare_corpus_study import public_rows, research_rows
from train_detector_revision import training_text, dump
from promption.filter.ensemble_filter import EnsembleFilter
from promption.filter.text_scoring import score_texts
from promption.training.calibration import binary_metrics
from promption.training.artifacts import file_sha256


def run():
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    directory = ROOT / "output/detector_revision_20261025/supplemental_v9"
    directory.mkdir(exist_ok=False)
    rows = [r for r in public_rows() if r["split"] == "val"]
    rows += [dict(id=r["id"], corpus="lumina", text=r["prompt"], label=r["injection_label_proposed"])
        for r in research_rows() if r["participant_split_proposed"] == "validation"
        and r["cohort"] == "post_reset" and not r["operational_exclusion"] and r["injection_label_proposed"] in (0, 1)]
    path = ROOT / "output/detector_revision_20261025/candidate_runtime.pkl"
    model = joblib.load(path)
    scores = score_texts(model["vectorizer"], model["classifier"], [training_text(r["text"]) for r in rows])
    engine = EnsembleFilter()
    baseline = [engine.analyze(r["text"], roles=["customer"]) for r in rows]
    blocked = np.array([r.blocked or r.ml is not None and r.ml.probability >= .75 for r in baseline])
    applicable = np.array([r.heuristic.signal != "benign" and not r.blocked for r in baseline])
    candidates = []
    for threshold in [.85, .9, .92, .94, .96, .97, .98, .99, .995, .999]:
        prediction = blocked | (applicable & (scores >= threshold))
        metrics = {}
        for c in ("public", "lumina"):
            index = np.array([r["corpus"] == c for r in rows])
            labels = np.array([r["label"] for r in rows])[index]
            metrics[c] = dict(before=binary_metrics(labels, blocked[index]), after=binary_metrics(labels, prediction[index]))
        feasible = all(r["after"]["fp"] == r["before"]["fp"] for r in metrics.values())
        gain = sum(r["before"]["fn"] - r["after"]["fn"] for r in metrics.values())
        candidates.append(dict(threshold=threshold, metrics=metrics, feasible=feasible, additional_tp=gain))
    dump(directory / "validation.json", dict(candidates=candidates, n=len(rows), api_calls=0,
        selection="Full single-turn public validation and all eligible Lumina validation turns, including contextual and lower-confidence labels. Maximize additional TP subject to zero additional FP in either corpus. Test is not consulted. Origins=user only; cumulative/tool ML stays unchanged.",
        model_sha256=file_sha256(path), source_labels="Unchanged source/provisional silver labels. Previously exposed regression."))
    feasible = [r for r in candidates if r["feasible"] and r["additional_tp"] > 0]
    if not feasible:
        print("No feasible supplemental detector. Runtime unchanged.")
        return
    selected = max(feasible, key=lambda r: (r["additional_tp"], r["threshold"]))
    dump(directory / "selection_before_test.json", selected)
    print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    run()
