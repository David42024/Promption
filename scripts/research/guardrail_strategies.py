"""Offline, grouped comparison of threshold, segmentation and domain adaptation."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold
import yaml

from prepare_candidates import words
from promption.filter.heuristic_filter import HeuristicFilter
from promption.filter.text_scoring import score_texts
from promption.training.artifacts import file_sha256
from promption.training.calibration import binary_metrics, choose_threshold
from promption.training.dataset import load_training_data
from promption.training.train_lightweight import train_lightweight_model
from promption.utils.config import load_config
from promption.utils.text import normalize_content


def components(frame):
    parent = list(range(len(frame)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for column in ("participant_id", "family_id"):
        seen = {}
        for i, value in enumerate(frame[column]):
            if value in seen:
                a, b = root(i), root(seen[value])
                parent[max(a, b)] = min(a, b)
            else:
                seen[value] = i
    return np.asarray([root(i) for i in range(len(frame))])


def near_index(texts):
    exact, grams, inverted = set(), [], defaultdict(list)
    for i, text in enumerate(texts):
        tokens = words(text)
        exact.add(" ".join(tokens))
        features = {tuple(tokens[j:j + 3]) for j in range(len(tokens) - 2)} if len(tokens) >= 8 else set()
        grams.append(features)
        for feature in features:
            inverted[feature].append(i)
    return exact, grams, inverted


def overlaps(text, index):
    exact, grams, inverted = index
    tokens = words(text)
    if " ".join(tokens) in exact:
        return True
    if len(tokens) < 8:
        return False
    features = {tuple(tokens[j:j + 3]) for j in range(len(tokens) - 2)}
    shared = Counter(i for feature in features for i in inverted.get(feature, []))
    return any(count / len(features | grams[i]) >= 0.8 for i, count in shared.items())


def prepare(folder):
    config = load_config()
    legacy = load_training_data()
    manifest = json.loads((Path(config["paths"]["processed_data"]) / "split_manifest.json").read_text())
    model = Path(config["model"]["lightweight_classifier_path"])
    metadata = json.loads(model.with_suffix(".metadata.json").read_text())
    if metadata["sha256"] != file_sha256(model) or metadata["manifest_hash"] != manifest["hash"]:
        raise ValueError("Existing model and frozen manifest must match")
    assignments = {record["group_id"]: record["partition"] for record in manifest["records"].values()}
    legacy["split"] = legacy["group_id"].map(assignments)
    unassigned = int(legacy["split"].isna().sum())
    old = {part: legacy[legacy["split"] == part].copy().reset_index(drop=True) for part in ("train", "val", "test")}
    annotations = {row["id"]: row for row in map(json.loads, (folder / "etiquetas_provisionales.jsonl").read_text().splitlines())}
    new = pd.read_csv(folder / "candidatos_entrenamiento_NO_GOLD.csv", encoding="utf-8-sig")
    new["prompt"] = new["id"].map(lambda key: annotations[key]["prompt"])
    degraded = new["prompt"].str.contains(r"\[[^\]]*REDACTAD[^\]]*\]", regex=True)
    excluded_degraded = int(degraded.sum())
    new = new[~degraded].copy()
    indices = {"train": near_index(pd.concat([old["val"], old["test"]])["prompt"]),
               "heldout": near_index(old["train"]["prompt"])}
    rejected = {row.family_id for row in new.itertuples() if overlaps(row.prompt, indices["train" if row.split == "train" else "heldout"])}
    overlap_count = int(new["family_id"].isin(rejected).sum())
    new = new[~new["family_id"].isin(rejected)].reset_index(drop=True)
    comp = {part: new[new["split"] == part].copy().reset_index(drop=True) for part in ("train", "validation", "test")}
    for left in comp:
        for right in comp:
            if left == right:
                continue
            for column in ("participant_id", "family_id"):
                if set(comp[left][column]) & set(comp[right][column]):
                    raise ValueError("Participant or family leaked between predefined research partitions")
    return old, comp, {"excluded_redacted": excluded_degraded, "excluded_cross_corpus_overlap": overlap_count,
                       "legacy_unassigned_rows_excluded": unassigned,
                       "current_legacy_csv_sha256": file_sha256(Path(config["paths"]["processed_data"]) / "training_data.csv"),
                       "annotation_sha256": file_sha256(folder / "etiquetas_provisionales.jsonl"),
                       "candidate_sha256": file_sha256(folder / "candidatos_entrenamiento_NO_GOLD.csv"),
                       "baseline_model_sha256": file_sha256(model), "legacy_manifest_hash": manifest["hash"]}


def observation(frame, scores):
    heuristic = HeuristicFilter()
    results = [heuristic.analyze(text) for text in frame["prompt"]]
    return {"labels": frame["label"].to_numpy(int), "scores": np.asarray(scores),
            "heuristic_blocked": np.asarray([r.blocked for r in results]),
            "explicit_benign": np.asarray([r.signal == "benign" for r in results])}


def measure(data, threshold):
    return binary_metrics(data["labels"], data["heuristic_blocked"] |
                          (~data["explicit_benign"] & (data["scores"] >= threshold)))


def fit(old_train, new_train, weight):
    frame = pd.concat([old_train, new_train], ignore_index=True)
    frame["prompt"] = frame["prompt"].map(normalize_content)
    weights = np.r_[np.ones(len(old_train)), np.full(len(new_train), weight)]
    vectorizer, classifier, _ = train_lightweight_model(frame, sample_weight=weights)
    return vectorizer, classifier


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = {"weights": [0.25, 1.0, 2.0], "inference": [
        {"normalize": True}, {"normalize": True, "chunk_chars": 500, "chunk_overlap": 100}],
        "cv": "three folds on connected participant/family groups, seed 42",
        "selection": "maximize mean recall on CV slices subject to neither slice increasing baseline FPR",
        "final_calibration": "selected strategy only, legacy validation and predefined competition validation",
        "labels": "provisional_silver_not_gold", "provider_calls": 0,
        "test_status": "held out from fitting and selection; previously exposed to rule-development diagnostics",
        "deployment": "experimental_opt_in_only"}
    dump(args.output / "protocol.json", protocol)
    old, comp, provenance = prepare(args.research)
    baseline = joblib.load(load_config()["model"]["lightweight_classifier_path"])
    score_old = lambda frame: score_texts(baseline["vectorizer"], baseline["classifier"], frame["prompt"].tolist())
    base_cv = {"legacy": observation(old["val"], score_old(old["val"])),
               "competition": observation(comp["train"], score_old(comp["train"]))}
    caps_cv = {name: measure(value, 0.66)["fpr"] for name, value in base_cv.items()}
    calibrated = choose_threshold(base_cv, fpr_caps=caps_cv)
    groups = components(comp["train"])
    folds = list(StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=42).split(
        comp["train"], comp["train"]["label"], groups))
    for train, val in folds:
        if set(groups[train]) & set(groups[val]) or comp["train"].iloc[val]["label"].nunique() != 2:
            raise ValueError("Grouped CV requires non-overlapping folds with both classes")
    split_records = {"legacy": {part: len(frame) for part, frame in old.items()},
                     "competition": {part: {"n": len(frame), "labels": frame["label"].value_counts().to_dict(),
                         "ids": frame["id"].tolist()} for part, frame in comp.items()},
                     "folds": [{"train_ids": comp["train"].iloc[tr]["id"].tolist(),
                                "validation_ids": comp["train"].iloc[va]["id"].tolist()} for tr, va in folds]}
    dump(args.output / "frozen_splits.json", split_records)
    dump(args.output / "provenance.json", provenance)
    candidates = []
    started = time.perf_counter()
    for weight in protocol["weights"]:
        cv_scores = [np.zeros(len(comp["train"])) for _ in protocol["inference"]]
        old_scores = [[] for _ in protocol["inference"]]
        for fold_index, (train_index, val_index) in enumerate(folds):
            vectorizer, classifier = fit(old["train"], comp["train"].iloc[train_index], weight)
            for mode, inference in enumerate(protocol["inference"]):
                cv_scores[mode][val_index] = score_texts(vectorizer, classifier,
                    comp["train"].iloc[val_index]["prompt"].tolist(), inference=inference)
                old_scores[mode].append(score_texts(vectorizer, classifier, old["val"]["prompt"].tolist(), inference=inference))
            print(f"weight={weight}, fold={fold_index + 1}/3 completed", flush=True)
        for mode, inference in enumerate(protocol["inference"]):
            data = {"legacy": {**base_cv["legacy"], "scores": np.mean(old_scores[mode], axis=0)},
                    "competition": {**base_cv["competition"], "scores": cv_scores[mode]}}
            result = choose_threshold(data, fpr_caps=caps_cv)
            selected = result["selected"]
            candidates.append({"weight": weight, "inference": inference, "calibration": result})
            print(json.dumps({"weight": weight, "inference": inference, "selected": selected}), flush=True)
        dump(args.output / "cross_validation.json", candidates)
    feasible = [candidate for candidate in candidates if candidate["calibration"]["selected"]]
    if not feasible:
        raise ValueError("No feasible adapted model; baseline left untouched")
    winner = max(feasible, key=lambda candidate: candidate["calibration"]["selected"]["mean_recall"])
    dump(args.output / "selection_before_test.json", winner)
    vectorizer, classifier = fit(old["train"], comp["train"], winner["weight"])
    final_val = {"legacy": observation(old["val"], score_texts(vectorizer, classifier,
                     old["val"]["prompt"].tolist(), inference=winner["inference"])),
                 "competition": observation(comp["validation"], score_texts(vectorizer, classifier,
                     comp["validation"]["prompt"].tolist(), inference=winner["inference"]))}
    original_val = {"legacy": base_cv["legacy"], "competition": observation(comp["validation"], score_old(comp["validation"]))}
    caps_final = {name: measure(value, 0.66)["fpr"] for name, value in original_val.items()}
    final_calibration = choose_threshold(final_val, fpr_caps=caps_final)
    original_calibration = choose_threshold(original_val, fpr_caps=caps_final)
    if not final_calibration["selected"]:
        raise ValueError("Final validation cannot meet FPR budgets; baseline left untouched")
    threshold = final_calibration["selected"]["threshold"]
    dump(args.output / "final_calibration_before_test.json", final_calibration)
    target = args.output / "adapted_classifier.pkl"
    joblib.dump({"vectorizer": vectorizer, "classifier": classifier, "model_type": "tfidf_logistic_regression",
                 "max_features": 10000, "inference": winner["inference"], "recommended_threshold": threshold,
                 "experimental": True, "annotation_status": "PROVISIONAL_REQUIRES_HUMAN_REVIEW"}, target)
    holdout = {}
    for name, frame in (("legacy", old["test"]), ("competition", comp["test"])):
        original = observation(frame, score_old(frame))
        adapted = observation(frame, score_texts(vectorizer, classifier, frame["prompt"].tolist(), inference=winner["inference"]))
        holdout[name] = {"baseline": measure(original, 0.66),
                         "threshold_only": measure(original, original_calibration["selected"]["threshold"]),
                         "adapted": measure(adapted, threshold)}
    metadata = {"experimental": True, "backend": "tfidf_logistic_regression", "sha256": file_sha256(target),
                "recommended_threshold": threshold, "inference": winner["inference"], "weight": winner["weight"],
                "provenance": provenance, "protocol": protocol, "heldout": holdout,
                "baseline_unchanged": file_sha256(Path(load_config()["model"]["lightweight_classifier_path"])) == provenance["baseline_model_sha256"],
                "elapsed_seconds": round(time.perf_counter() - started, 2)}
    dump(target.with_suffix(".metadata.json"), metadata)
    dump(args.output / "results.json", metadata)
    profile = deepcopy(load_config())
    profile["model"]["lightweight_classifier_path"] = str(target.resolve())
    profile["ensemble"]["decision_high_threshold"] = threshold
    profile["model"]["confidence_threshold"] = threshold
    profile["classification"]["ml_malicious_threshold"] = threshold
    (args.output / "experimental_config.yaml").write_text(yaml.safe_dump(profile, allow_unicode=True))
    print(json.dumps({"heldout": holdout, "threshold": threshold, "weight": winner["weight"],
                      "inference": winner["inference"], "baseline_unchanged": metadata["baseline_unchanged"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
