"""Exploratory supplemental detector preserving every veto of the original model."""
import argparse
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
import yaml

from guardrail_strategies import prepare, observation, measure, dump
from promption.filter.text_scoring import score_texts
from promption.training.calibration import choose_threshold
from promption.utils.config import load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    old, comp, provenance = prepare(args.research)
    baseline = joblib.load(load_config()["model"]["lightweight_classifier_path"])
    path = args.experiment / "adapted_classifier.pkl"
    adapted = joblib.load(path)
    protocol = {"method": "fixed_base_detector_OR_calibrated_supplemental_detector",
                "status": "exploratory_followup_after_single_model_holdout_was_observed",
                "selection_data": "predefined validation partitions only",
                "threshold_grid": list(np.arange(0.67, 1, 0.01).round(2)),
                "base_threshold": 0.66, "labels": "provisional_silver_not_gold",
                "provider_calls": 0, "deployment": "opt_in_only"}
    dump(args.experiment / "supplemental_protocol_before_replay.json", protocol)

    def observations(frame):
        original = observation(frame, score_texts(baseline["vectorizer"], baseline["classifier"], frame["prompt"].tolist()))
        scores = score_texts(adapted["vectorizer"], adapted["classifier"], frame["prompt"].tolist(), inference=adapted["inference"])
        baseline_veto = original["heuristic_blocked"] | (~original["explicit_benign"] & (original["scores"] >= 0.66))
        return original, {**original, "scores": scores, "heuristic_blocked": baseline_veto}

    originals, validation = {}, {}
    for name, frame in (("legacy", old["val"]), ("competition", comp["validation"])):
        originals[name], validation[name] = observations(frame)
    caps = {name: measure(value, 0.66)["fpr"] for name, value in originals.items()}
    calibration = choose_threshold(validation, fpr_caps=caps, thresholds=protocol["threshold_grid"])
    dump(args.experiment / "supplemental_calibration_before_replay.json", calibration)
    if not calibration["selected"]:
        print("No feasible supplemental profile; baseline unchanged")
        return
    threshold = calibration["selected"]["threshold"]
    metrics = {}
    for name, frame in (("legacy", old["test"]), ("competition", comp["test"])):
        original, supplemental = observations(frame)
        metrics[name] = {"baseline": measure(original, 0.66), "supplemental": measure(supplemental, threshold)}
    result = {"protocol": protocol, "threshold": threshold, "metrics": metrics, "provenance": provenance}
    dump(args.experiment / "supplemental_results.json", result)
    profile = load_config().copy()
    profile["ensemble"] = {**profile["ensemble"], "additional_classifiers": [
        {"model_path": str(path.resolve()), "threshold": threshold}]}
    (args.experiment / "supplemental_config.yaml").write_text(yaml.safe_dump(profile, allow_unicode=True))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
