"""Retrain the lightweight classifier with Spanish data and unchanged holdouts."""
import argparse
from copy import deepcopy
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

from promption.training.artifacts import file_sha256, preserve_records
from promption.training.dataset import load_training_data
from promption.training.spanish_corpus import SOURCE, build_spanish_corpus
from promption.training.spanish_translation import validate_translations
from promption.training.split import create_splits, calculate_manifest_hash
from promption.training import train_lightweight as training
from promption.utils.config import load_config
from promption.utils.logger import logger
from scripts.retrain_spanish_model import summarize_partitions


def combine(base, translations, manifest, curated_variants):
    """Append validated Spanish rows without moving a single existing family."""
    validate_translations(translations, base, manifest)
    curated = build_spanish_corpus().groupby("family_id", sort=False).head(curated_variants).copy()
    curated["group_id"] = curated.family_id
    if set(base.group_id) & set(curated.group_id):
        raise ValueError("Curated Spanish families have already been installed")
    df = pd.concat([base, curated, translations], ignore_index=True)
    if df.prompt.duplicated().any():
        raise ValueError("Augmentation contains duplicate prompts")
    parts = create_splits(df, seed=manifest["seed"])
    old = {r["group_id"]: r["partition"] for r in manifest["records"].values()}
    for name, indices in zip(("train", "val", "test", "external"), parts):
        if any(old.get(g) != name for g in df.iloc[indices[indices < len(base)]].group_id):
            raise ValueError("Augmentation moved an existing evaluation family")
    if not set(range(len(base), len(df))).issubset(set(parts[0])):
        raise ValueError("Augmentation escaped the training partition")
    return df, parts, curated


def scores(artifact, data):
    pos = int(np.flatnonzero(artifact["classifier"].classes_ == 1)[0])
    return artifact["classifier"].predict_proba(artifact["vectorizer"].transform(data.prompt.tolist()))[:, pos]


def combine_additional(base, additional, manifest):
    """Install reviewed families without using or moving existing holdout cases."""
    required = {"prompt", "label", "source", "lang", "family_id"}
    if not required.issubset(additional.columns) or additional.empty:
        raise ValueError("Reviewed corpus is missing required rows or columns")
    if additional[list(required)].isna().any().any():
        raise ValueError("Reviewed corpus contains missing values")
    if not additional.source.eq(SOURCE).all() or not additional.lang.eq("es").all():
        raise ValueError("Reviewed corpus must use the Spanish training-only source")
    if not additional.label.isin([0, 1]).all() or additional.groupby("family_id").label.nunique().gt(1).any():
        raise ValueError("Reviewed family labels are inconsistent")
    if additional.prompt.str.strip().eq("").any() or additional.family_id.str.strip().eq("").any():
        raise ValueError("Reviewed text and family identifiers must be nonempty")
    additional = additional.copy()
    additional["group_id"] = additional.family_id
    if set(base.group_id) & set(additional.group_id):
        raise ValueError("Reviewed families have already been installed")
    df = pd.concat([base, additional], ignore_index=True)
    if df.prompt.duplicated().any():
        raise ValueError("Reviewed corpus overlaps existing prompts")
    parts = create_splits(df, seed=manifest["seed"])
    old = {r["group_id"]: r["partition"] for r in manifest["records"].values()}
    for name, indices in zip(("train", "val", "test", "external"), parts):
        if any(old.get(g) != name for g in df.iloc[indices[indices < len(base)]].group_id):
            raise ValueError("Reviewed corpus moved an evaluation family")
    if not set(range(len(base), len(df))).issubset(set(parts[0])):
        raise ValueError("Reviewed corpus escaped the training partition")
    return df, parts, df.loc[df.source.eq(SOURCE)].copy()


def validation_checks(before, after):
    """Require preserved recall and bounded FPR at the unchanged deployed threshold."""
    return {"recall_not_worse": after["all"]["recall"] >= before["all"]["recall"],
            "FPR_within_one_percentage_point": after["all"]["FPR"] <= before["all"]["FPR"] + .01,
            "spanish_recall_not_worse": after["es"]["recall"] >= before["es"]["recall"],
            "spanish_FPR_not_worse": after["es"]["FPR"] <= before["es"]["FPR"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--translations", type=Path)
    parser.add_argument("--additional-corpus", type=Path)
    parser.add_argument("--curated-variants", type=int, choices=[0, 1, 3, 12], default=1)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if not args.execute:
        parser.print_help()
        return 0
    logger.disabled = True
    config = deepcopy(load_config())
    if not config["model"].get("use_lightweight_ml"):
        raise ValueError("The active backend must be lightweight")
    output = args.output_dir or Path(config["paths"]["results"]) / (
        "spanish-light-retrain-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    output.mkdir(parents=True, exist_ok=False)
    processed = Path(config["paths"]["processed_data"])
    manifest = json.loads((processed / "split_manifest.json").read_text())
    if calculate_manifest_hash(manifest) != manifest.get("hash"):
        raise ValueError("The active manifest is corrupt")
    original_path = Path(config["model"]["lightweight_classifier_path"])
    original_meta = json.loads(original_path.with_suffix(".metadata.json").read_text())
    if original_meta.get("sha256") != file_sha256(original_path) or original_meta.get("manifest_hash") != manifest["hash"]:
        raise ValueError("The original model is not linked to the active manifest")
    base = load_training_data()
    if args.additional_corpus:
        translations = pd.read_csv(Path(config["paths"]["raw_data"]) / "spanish_translations.csv")
        df, parts, curated = combine_additional(base, pd.read_csv(args.additional_corpus), manifest)
    else:
        if not args.translations:
            raise ValueError("Provide --translations or --additional-corpus")
        translations = pd.read_csv(args.translations)
        df, parts, curated = combine(base, translations, manifest, args.curated_variants)
    df.to_csv(output / "training_data.csv", index=False)
    curated.to_csv(output / "spanish_augmentation.csv", index=False)
    translations.to_csv(output / "spanish_translations.csv", index=False)
    threshold = config["ensemble"]["decision_high_threshold"]
    baseline = summarize_partitions(df, parts, scores(joblib.load(original_path), df), threshold)
    isolated = deepcopy(config)
    isolated["paths"]["processed_data"] = str(output / "processed")
    isolated["paths"]["results"] = str(output / "metrics")
    Path(isolated["paths"]["processed_data"]).mkdir()
    for filename in ("translation_links.json", "label_overrides.csv", "quarantine.csv"):
        if (processed / filename).exists():
            shutil.copy2(processed / filename, Path(isolated["paths"]["processed_data"]) / filename)
    candidate = output / original_path.name
    original_conf = training._CONF
    training._CONF = isolated
    try:
        metadata = training.train(str(output / "training_data.csv"), candidate, preserve=False)
    finally:
        training._CONF = original_conf
    after = summarize_partitions(df, parts, scores(joblib.load(candidate), df), threshold)
    checks = validation_checks(baseline["val"], after["val"])
    report = {"backend": "tfidf_logistic_regression", "threshold": threshold,
        "added_rows": len(df) - len(base),
        "additional_corpus_sha256": file_sha256(args.additional_corpus) if args.additional_corpus else None,
        "translated_rows": len(translations), "translated_families": translations.group_id.nunique(),
        "curated_rows": len(curated), "curated_families": curated.family_id.nunique(),
        "original_families_unchanged": True, "before": baseline, "after": after,
        "validation_checks": checks, "eligible": all(checks.values()), "activated": False}
    metadata.update(translation_source="translated_train_es_v1", translation_rows=len(translations),
        translation_corpus_sha256=file_sha256(output / "spanish_translations.csv"),
        language_metrics=after, validation_activation_checks=checks)
    candidate.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if args.activate and all(checks.values()):
        backup = preserve_records(config)
        for filename in ("training_data.csv", "split_manifest.json"):
            shutil.copy2(processed / filename, backup / filename)
        for filename in ("spanish_augmentation.csv", "spanish_translations.csv"):
            existing = Path(config["paths"]["raw_data"]) / filename
            if existing.exists():
                shutil.copy2(existing, backup / filename)
        shutil.copy2(candidate, original_path)
        shutil.copy2(candidate.with_suffix(".metadata.json"), original_path.with_suffix(".metadata.json"))
        shutil.copy2(output / "processed/split_manifest.json", processed / "split_manifest.json")
        shutil.copy2(output / "training_data.csv", processed / "training_data.csv")
        for filename in ("spanish_augmentation.csv", "spanish_translations.csv"):
            if filename != "spanish_augmentation.csv" or len(curated):
                shutil.copy2(output / filename, Path(config["paths"]["raw_data"]) / filename)
        for filename in ("model_metrics.csv", "model_metrics_tfidf.csv"):
            shutil.copy2(output / "metrics" / filename, Path(config["paths"]["results"]) / filename)
        report.update(activated=True, backup=str(backup))
    (output / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if not args.activate or report["activated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
