"""Train and compare a Spanish-enriched multilingual forest on unchanged holdouts."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.ensemble import RandomForestClassifier

from promption.training.artifacts import file_sha256, preserve_records
from promption.training.dataset import load_training_data
from promption.training.spanish_corpus import SOURCE, build_spanish_corpus
from promption.training.split import create_splits, calculate_manifest_hash
from promption.utils.config import load_config
from promption.utils.logger import logger


def metrics(y, scores, threshold):
    """Measure block decisions, retaining their positive and negative denominators."""
    tn, fp, fn, tp = confusion_matrix(y, scores >= threshold, labels=[0, 1]).ravel()
    return {"n": len(y), "threshold": threshold,
            "TP": int(tp), "TN": int(tn), "FP": int(fp), "FN": int(fn),
            "recall": float(tp / (tp + fn)) if tp + fn else None,
            "FPR": float(fp / (tn + fp)) if tn + fp else None}


def summarize_partitions(df, parts, scores, threshold):
    result = {}
    for name, indices in zip(("train", "val", "test", "external"), parts):
        if name == "train":
            continue
        result[name] = {}
        for language in ("all", "es", "en"):
            chosen = indices if language == "all" else indices[df.iloc[indices].lang.to_numpy() == language]
            result[name][language] = metrics(df.iloc[chosen].label.to_numpy(int), scores[chosen], threshold)
    return result


def augment_preserving_holdouts(base, old_manifest):
    """Append only newly authored train families, never reassign existing groups."""
    augmentation = build_spanish_corpus()
    augmentation["group_id"] = augmentation.family_id
    if set(base.prompt) & set(augmentation.prompt) or set(base.group_id) & set(augmentation.group_id):
        raise ValueError("Spanish augmentation overlaps an existing prompt or family")
    combined = pd.concat([base, augmentation], ignore_index=True)
    parts = create_splits(combined, seed=int(old_manifest["seed"]))
    old_partitions = {v["group_id"]: v["partition"] for v in old_manifest["records"].values()}
    for name, indices in zip(("train", "val", "test", "external"), parts):
        for group in combined.iloc[indices[indices < len(base)]].group_id:
            if old_partitions.get(group) != name:
                raise ValueError("Retraining would change an existing evaluation family")
    if set(np.concatenate(parts)) != set(range(len(combined))):
        raise ValueError("Split coverage is incomplete")
    return combined, parts, augmentation


def encode_deployed_holdouts(df, parts, config, output):
    """Use the same sentence windows and max probability as MLFilter.analyze."""
    from promption.filter.ml_filter import chunk_text
    from promption.training.train import embed_dataset
    selected = np.concatenate(parts[1:])
    texts, owners = [], []
    for i in selected:
        chunks = chunk_text(df.iloc[i].prompt, config["model"].get("chunk_chars", 250),
                            config["model"].get("chunk_overlap", 100))
        texts.extend(chunks)
        owners.extend([int(i)] * len(chunks))
    vectors = embed_dataset(pd.DataFrame({"prompt": texts}), config["model"]["embedding_model"],
                            output / "holdout_windows.npy")
    return vectors, np.asarray(owners, dtype=int)


def tune_on_validation(train_vectors, train_labels, val_vectors, val_owners,
                       val_labels, val_languages, baseline, threshold, config, output):
    """Choose forest parameters using train rows and validation windows only."""
    grid = [(0.25, None), (0.5, None), (0.25, {0: 1, 1: 2}),
            (0.5, {0: 1, 1: 2}), (1.0, None)]
    candidates = []
    winner = None
    for max_features, class_weight in grid:
        classifier = RandomForestClassifier(n_estimators=config["model"]["n_trees"],
            max_depth=config["model"]["max_depth"], min_samples_leaf=config["model"]["min_samples_leaf"],
            random_state=config["model"]["random_state"], n_jobs=-1,
            max_features=max_features, class_weight=class_weight)
        print(f"Validation tuning: max_features={max_features}, class_weight={class_weight}", flush=True)
        classifier.fit(train_vectors, train_labels)
        pos = int(np.flatnonzero(classifier.classes_ == 1)[0])
        scores = np.zeros(len(val_labels))
        np.maximum.at(scores, val_owners, classifier.predict_proba(val_vectors)[:, pos])
        overall = metrics(val_labels, scores, threshold)
        spanish = metrics(val_labels[val_languages == "es"], scores[val_languages == "es"], threshold)
        eligible = (overall["recall"] >= baseline["all"]["recall"]
                    and overall["FPR"] <= baseline["all"]["FPR"] + .02
                    and spanish["recall"] >= baseline["es"]["recall"])
        candidates.append({"max_features": max_features, "class_weight": class_weight,
                           "validation": overall, "validation_es": spanish, "eligible": bool(eligible)})
        (output / "validation_tuning.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
        print(json.dumps(candidates[-1]), flush=True)
        if eligible:
            winner = classifier
            break
    return winner


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume-output", type=Path)
    parser.add_argument("--tune-validation", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.print_help()
        return 0
    logger.disabled = True
    import torch
    torch.set_num_threads(min(8, torch.get_num_threads()))
    from promption.training import train as forest
    config = deepcopy(load_config())
    output = args.resume_output or args.output_dir or Path(config["paths"]["results"]) / (
        "spanish-retrain-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    output.mkdir(parents=True, exist_ok=bool(args.resume_output))
    processed = Path(config["paths"]["processed_data"])
    old_manifest = json.loads((processed / "split_manifest.json").read_text(encoding="utf-8"))
    if calculate_manifest_hash(old_manifest) != old_manifest.get("hash"):
        raise ValueError("Existing split manifest is corrupt")
    base = load_training_data()
    if base.source.eq(SOURCE).any():
        raise ValueError("This v1 augmentation has already been applied; use a new version")
    df, parts, augmentation = augment_preserving_holdouts(base, old_manifest)
    backup = preserve_records(config)
    for filename in ("training_data.csv", "split_manifest.json"):
        shutil.copy2(processed / filename, backup / filename)
    shutil.copy2(Path(config["paths"]["cfg"]), backup / "config.yaml")
    backup_resources = ROOT / "promption/resources/config.yaml"
    if backup_resources.is_file():
        shutil.copy2(backup_resources, backup / "resources_config.yaml")
    df.to_csv(output / "training_data.csv", index=False, encoding="utf-8")
    augmentation.drop(columns="group_id").to_csv(output / "spanish_augmentation.csv", index=False, encoding="utf-8")
    baseline = joblib.load(config["model"]["lightweight_classifier_path"])
    baseline_path = Path(config["model"]["lightweight_classifier_path"])
    baseline_meta = json.loads(baseline_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    if baseline_meta.get("sha256") != file_sha256(baseline_path) or baseline_meta.get("manifest_hash") != old_manifest["hash"]:
        raise ValueError("Baseline model provenance does not match the existing manifest")
    pos = int(np.flatnonzero(baseline["classifier"].classes_ == 1)[0])
    light_scores = baseline["classifier"].predict_proba(baseline["vectorizer"].transform(df.prompt.tolist()))[:, pos]
    threshold = float(config["ensemble"]["decision_high_threshold"])
    before = summarize_partitions(df, parts, light_scores, threshold)
    isolated = deepcopy(config)
    isolated["model"]["use_lightweight_ml"] = False
    isolated["paths"]["processed_data"] = str(output / "processed")
    isolated["paths"]["results"] = str(output / "metrics")
    isolated["paths"]["plots"] = str(output / "plots")
    Path(isolated["paths"]["plots"]).mkdir(exist_ok=bool(args.resume_output))
    Path(isolated["paths"]["processed_data"]).mkdir(exist_ok=True)
    for name in ("translation_links.json", "quarantine.csv", "label_overrides.csv"):
        if (processed / name).is_file():
            shutil.copy2(processed / name, Path(isolated["paths"]["processed_data"]) / name)
    candidate = output / "random_forest.pkl"
    original_config = forest._CONF
    forest._CONF = isolated
    try:
        print(f"Training multilingual forest: {len(df)} rows; results: {output.resolve()}", flush=True)
        if not args.resume_output:
            forest.main(out_path=str(candidate), data_path=output / "training_data.csv", preserve=False)
        else:
            metadata = json.loads(candidate.with_suffix(".metadata.json").read_text(encoding="utf-8"))
            if metadata["sha256"] != file_sha256(candidate):
                raise ValueError("Resumed candidate checksum mismatch")
            prepared = pd.read_csv(output / "training_data.csv", encoding="utf-8")
            expected_dataset = hashlib.sha256(prepared.to_csv(index=False).encode("utf-8")).hexdigest()
            if metadata["dataset_sha256"] != expected_dataset:
                raise ValueError("Resumed candidate was trained on different data")
            expected_encoder = forest.embedding_fingerprint(prepared, config["model"]["embedding_model"],
                config["model"].get("embedding_prefix", ""), config["model"].get("embedding_revision"))
            if metadata["embedding_cache_fingerprint"] != expected_encoder:
                raise ValueError("Resumed candidate uses a different encoder contract")
    finally:
        forest._CONF = original_config
    classifier = joblib.load(candidate)
    vectors, owners = encode_deployed_holdouts(df, parts, config, output)
    if args.tune_validation:
        from promption.training.train import embedding_fingerprint, embed_dataset
        fingerprint = embedding_fingerprint(df, config["model"]["embedding_model"],
            config["model"].get("embedding_prefix", ""), config["model"].get("embedding_revision"))
        cache = Path(config["paths"]["raw_data"]).parent / f"embeddings_train_{fingerprint[:16]}.npy"
        training_vectors = embed_dataset(df, config["model"]["embedding_model"], cache)
        val_indices = parts[1]
        selected = np.isin(owners, val_indices)
        position = {int(row): i for i, row in enumerate(val_indices)}
        val_owners = np.asarray([position[int(row)] for row in owners[selected]])
        winner = tune_on_validation(training_vectors[parts[0]], df.iloc[parts[0]].label.to_numpy(int),
            vectors[selected], val_owners, df.iloc[val_indices].label.to_numpy(int),
            df.iloc[val_indices].lang.to_numpy(), before["val"], threshold, config, output)
        if winner is not None:
            shutil.copy2(candidate, output / "initial_random_forest.pkl")
            shutil.copy2(candidate.with_suffix(".metadata.json"), output / "initial_random_forest.metadata.json")
            if (output / "comparison.json").is_file():
                shutil.copy2(output / "comparison.json", output / "initial_comparison.json")
            classifier = winner
            joblib.dump(classifier, candidate)
    scores = np.zeros(len(df))
    pos = int(np.flatnonzero(classifier.classes_ == 1)[0])
    np.maximum.at(scores, owners, classifier.predict_proba(vectors)[:, pos])
    after = summarize_partitions(df, parts, scores, threshold)
    old_val, new_val = before["val"]["all"], after["val"]["all"]
    checks = {"validation_recall_not_worse": new_val["recall"] >= old_val["recall"],
              "validation_FPR_within_two_percentage_points": new_val["FPR"] <= old_val["FPR"] + .02,
              "spanish_validation_recall_not_worse": after["val"]["es"]["recall"] >= before["val"]["es"]["recall"]}
    new_meta = json.loads(candidate.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    new_meta["sha256"] = file_sha256(candidate)
    new_meta["classifier_parameters"] = classifier.get_params()
    new_meta["encoder_runtime_versions"] = forest.encoder_runtime_versions()
    if args.tune_validation and winner is not None:
        full_scores = classifier.predict_proba(training_vectors)[:, int(np.flatnonzero(classifier.classes_ == 1)[0])]
        for name, key, indices in (("test", "metrics", parts[2]), ("val", "val_metrics", parts[1])):
            current = metrics(df.iloc[indices].label.to_numpy(int), full_scores[indices], threshold)
            tp, tn, fp, fn = (current[k] for k in ("TP", "TN", "FP", "FN"))
            new_meta[key].update(accuracy=(tp + tn) / current["n"], recall=current["recall"],
                precision=tp / (tp + fp) if tp + fp else 0,
                f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
                false_positive_rate=current["FPR"], roc_auc=float(roc_auc_score(df.iloc[indices].label, full_scores[indices])))
    if not args.resume_output or (args.tune_validation and winner is not None):
        new_meta["full_text_metrics"] = new_meta["metrics"].copy()
        new_meta["full_text_val_metrics"] = new_meta["val_metrics"].copy()
    for partition, key, indices in (("test", "metrics", parts[2]), ("val", "val_metrics", parts[1])):
        current = after[partition]["all"]
        tp, tn, fp, fn = (current[k] for k in ("TP", "TN", "FP", "FN"))
        new_meta[key].update(accuracy=(tp + tn) / current["n"], recall=current["recall"],
                             precision=tp / (tp + fp) if tp + fp else 0,
                             f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
                             false_positive_rate=current["FPR"],
                             roc_auc=float(roc_auc_score(df.iloc[indices].label, scores[indices])),
                             evaluation_mode="deployed_sentence_window_max")
    new_meta["metrics"]["backend"] = "embeddings_random_forest"
    for lang in ("es", "en"):
        current = after["test"][lang]
        tp, tn, fp, fn = (current[k] for k in ("TP", "TN", "FP", "FN"))
        new_meta["metrics"].update({f"recall_{lang}": current["recall"],
                                    f"accuracy_{lang}": (tp + tn) / current["n"],
                                    f"precision_{lang}": tp / (tp + fp) if tp + fp else 0,
                                    f"f1_{lang}": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0})
    for name in ("model_metrics.csv", "model_metrics_embeddings_random_forest.csv"):
        pd.DataFrame([new_meta["metrics"]]).to_csv(output / "metrics" / name, index=False)
    new_meta["deployed_window_metrics"] = after
    new_meta["training_corpus_sha256"] = file_sha256(output / "spanish_augmentation.csv")
    candidate.with_suffix(".metadata.json").write_text(json.dumps(new_meta, indent=2), encoding="utf-8")
    report = {"baseline_backend": "tfidf_logistic_regression", "candidate_backend": "embeddings_random_forest",
              "encoder": config["model"]["embedding_model"], "threshold_unchanged": threshold,
              "baseline_sha256": baseline_meta["sha256"], "candidate_sha256": new_meta["sha256"],
              "backup": str(backup), "augmentation_rows": len(augmentation), "augmentation_families": augmentation.family_id.nunique(),
              "previous_evaluation_families_unchanged": True, "before": before, "after": after,
              "activation_checks_based_only_on_validation": checks, "activated": False,
              "note": "Authored synthetic training variants are not independent evaluation samples. Backend and training data both changed."}
    if args.activate and all(checks.values()):
        shutil.copy2(candidate, config["model"]["classifier_path"])
        shutil.copy2(candidate.with_suffix(".metadata.json"), Path(config["model"]["classifier_path"]).with_suffix(".metadata.json"))
        shutil.copy2(output / "processed/split_manifest.json", processed / "split_manifest.json")
        shutil.copy2(output / "training_data.csv", processed / "training_data.csv")
        shutil.copy2(output / "spanish_augmentation.csv", Path(config["paths"]["raw_data"]) / "spanish_augmentation.csv")
        for path in (Path(config["paths"]["cfg"]), ROOT / "promption/resources/config.yaml"):
            text = path.read_text(encoding="utf-8")
            import re
            text = re.sub(r"(?m)^  use_lightweight_ml:.*$", "  use_lightweight_ml: false", text)
            if args.tune_validation and winner is not None:
                import yaml
                for name in ("max_features", "class_weight"):
                    entry = yaml.safe_dump({name: classifier.get_params()[name]}, default_flow_style=True).strip()[1:-1]
                    pattern = rf"(?m)^  {name}:.*$"
                    if re.search(pattern, text):
                        text = re.sub(pattern, "  " + entry, text)
                    else:
                        text = text.replace("  use_lightweight_ml: false", "  use_lightweight_ml: false\n  " + entry)
            path.write_text(text, encoding="utf-8")
        for name in ("model_metrics.csv", "model_metrics_embeddings_random_forest.csv"):
            shutil.copy2(output / "metrics" / name, Path(config["paths"]["results"]) / name)
        report["activated"] = True
    (output / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if not args.activate or report["activated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
