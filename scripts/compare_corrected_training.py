"""Compare Spanish, English and bilingual lightweight models on corrected holdouts."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, accuracy_score, precision_score, roc_auc_score

from promption.utils.config import load_config
from promption.training.artifacts import file_sha256, preserve_records
from promption.training.reviewed_dataset import load_reviewed_dataset, connect_families, reserve_test_cases
from promption.training.split import save_manifest
from promption.training.train_lightweight import train_lightweight_model
from scripts.retrain_lightweight_spanish import scores
from scripts.retrain_spanish_model import metrics


def evaluate(artifact, data, threshold):
    result = {}
    for language in ("all", "es", "en"):
        for origin in ("all", "original", "synthetic"):
            selected = data if language == "all" else data[data.lang.eq(language)]
            if origin != "all":
                mask = selected.generation_method.eq("original_corrected")
                selected = selected[mask if origin == "original" else ~mask]
            if selected.empty:
                continue
            probability = scores(artifact, selected)
            measured = metrics(selected.label.to_numpy(int), probability, threshold)
            measured["f1"] = float(f1_score(selected.label, probability >= threshold, zero_division=0))
            measured["accuracy"] = float(accuracy_score(selected.label, probability >= threshold))
            measured["precision"] = float(precision_score(selected.label, probability >= threshold, zero_division=0))
            measured["auc"] = float(roc_auc_score(selected.label, probability)) if selected.label.nunique() == 2 else None
            measured["roc_auc"] = measured["auc"]
            measured["fpr"] = measured["FPR"]
            result[f"{language}/{origin}"] = measured
    return result


def validation_rank(measured):
    """Choose using original validation rows, weighting both languages equally."""
    return (np.mean([measured[f"{lang}/original"]["f1"] for lang in ("es", "en")]),
            np.mean([measured[f"{lang}/all"]["f1"] for lang in ("es", "en")]))


def replace_path(path, key, value):
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    replacement = f'  {key}: "{value}"'
    existing = next((i for i, line in enumerate(lines) if line.startswith(f"  {key}:")), None)
    if existing is not None:
        lines[existing] = replacement
    else:
        lines.insert(lines.index("paths:") + 1, replacement)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/processed/archivos_validos/dataset_corregido_bilingue.csv")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cases", type=int, default=200)
    parser.add_argument("--training-mode", choices=["compare", "bilingual"], default="compare")
    parser.add_argument("--benchmark-language", choices=["es", "en", "all"], default="es")
    parser.add_argument("--reserve-test", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.print_help()
        return 0
    if args.cases < 2 or args.cases % 2:
        parser.error("--cases must be positive and even for balanced sampling")
    config = deepcopy(load_config())
    config["logging"]["file"] = None
    load_config()["logging"]["file"] = None
    from promption.utils.logger import logger
    logger.disabled = True
    if not config["model"].get("use_lightweight_ml"):
        raise ValueError("This comparison requires the lightweight backend")
    output = Path(config["paths"]["results"]) / ("corrected-language-comparison-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    output.mkdir(parents=True, exist_ok=False)
    data, changed = connect_families(load_reviewed_dataset(args.data))
    reserved_rows = 0
    if args.reserve_test:
        data, reserved_rows = reserve_test_cases(data, args.cases // 2, args.seed, args.benchmark_language)
    data.to_csv(output / "training_data.csv", index=False)
    partitions = tuple(np.flatnonzero(data.split.eq(name).to_numpy()) for name in ("train", "val", "test", "external"))
    if sum(map(len, partitions)) != len(data):
        raise ValueError("Incomplete partition coverage")
    for group, records in data.groupby("group_id"):
        if records.split.nunique() != 1:
            raise ValueError("A connected family crossed partitions")
    manifest = save_manifest(data, *partitions, seed=args.seed, out_dir=output)
    threshold = float(config["ensemble"]["decision_high_threshold"])
    val = data.iloc[partitions[1]]
    test = data.iloc[partitions[2]]
    candidates = {}
    artifacts = {}
    conditions = (("spanish", ["es"]), ("english", ["en"]), ("bilingual", ["es", "en"]))
    if args.training_mode == "bilingual":
        conditions = (("bilingual", ["es", "en"]),)
    for name, languages in conditions:
        train = data.iloc[partitions[0]]
        train = train[train.lang.isin(languages)]
        if train.label.nunique() != 2:
            raise ValueError("Each training condition needs both classes")
        vectorizer, classifier, _ = train_lightweight_model(train)
        artifact = dict(vectorizer=vectorizer, classifier=classifier, model_type="tfidf_logistic_regression",
                        feature_mode="word_and_char_ngrams", max_features=10000)
        path = output / f"{name}.pkl"
        joblib.dump(artifact, path)
        validation = evaluate(artifact, val, threshold)
        artifacts[name] = artifact
        candidates[name] = dict(train_rows=len(train), training_distribution=train.groupby(["lang", "label"]).size().reset_index(name="count").to_dict("records"),
                                validation=validation, validation_rank=list(validation_rank(validation)), model_path=str(path))
        print(f"Trained {name}: {len(train)} rows", flush=True)
    winner = max(candidates, key=lambda name: validation_rank(candidates[name]["validation"]))
    for name, details in candidates.items():
        details["test"] = evaluate(artifacts[name], test, threshold)
        path = Path(details["model_path"])
        details["test"]["all/all"].update(n_train=details["train_rows"], n_val=len(val), n_test=len(test), n_samples=len(data), backend="tfidf_logistic_regression")
        artifacts[name].update(metrics=details["test"]["all/all"], val_metrics=details["validation"]["all/all"])
        joblib.dump(artifacts[name], path)
        metadata = dict(backend="tfidf_logistic_regression", sha256=file_sha256(path),
                        dataset_sha256=file_sha256(output / "training_data.csv"), source_dataset_sha256=file_sha256(args.data),
                        manifest_hash=manifest["hash"], manifest_splits=manifest["splits"], seed=args.seed,
                        trained_at=datetime.now(timezone.utc).isoformat(), training_language=name,
                        training_distribution=details["training_distribution"], actual_train_rows=details["train_rows"],
                        metrics=details["test"]["all/all"], val_metrics=details["validation"]["all/all"],
                        language_metrics=dict(validation=details["validation"], test=details["test"]),
                        selection="previous comparison selected bilingual; fixed before final test" if args.training_mode == "bilingual" else "original validation macro F1 across es/en; fixed threshold")
        path.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    benchmark_pool = test if args.benchmark_language == "all" else test[test.lang.eq(args.benchmark_language)]
    selected = pd.concat([benchmark_pool[benchmark_pool.label.eq(label)].sample(n=args.cases // 2, random_state=args.seed)
                          for label in (0, 1)], ignore_index=True).sample(frac=1, random_state=args.seed).reset_index(drop=True)
    selected["partition"] = "test"
    selected["manifest_hash"] = manifest["hash"]
    selected.to_json(output / "selected_cases.jsonl", orient="records", lines=True, force_ascii=False)
    from promption.filter.ensemble_filter import build_default
    from promption.filter.ml_filter_lightweight import LightMLFilter
    from promption.benchmark.runner import BenchmarkRunner, RunnerOptions
    filters = build_default()
    filters.ml = LightMLFilter(model_path=candidates[winner]["model_path"], threshold=threshold)
    results, measured = BenchmarkRunner(filter=filters, opts=RunnerOptions(data=selected, use_llm=False, use_ml=True,
        sample_size=args.cases, seed=args.seed, save=True, results_dir=output / "benchmark", partition="test",
        manifest_hash=manifest["hash"], evaluation_mode="proxy", run_id=output.name)).run()
    results["language"] = selected.lang
    results["generation_method"] = selected.generation_method
    results["standalone_ml_probability"] = scores(artifacts[winner], selected)
    results["standalone_ml_blocked"] = results.standalone_ml_probability >= threshold
    results["false_positive"] = results.label.eq(0) & results.filter_blocked.astype(bool)
    results["false_negative_block_decision"] = results.label.eq(1) & ~results.filter_blocked.astype(bool)
    results.to_csv(output / "benchmark/measured_cases.csv", index=False)
    results[results.false_positive | results.false_negative_block_decision].to_csv(output / "benchmark/errors.csv", index=False)
    if len(results) != args.cases or not results.provider_calls.fillna(0).eq(0).all():
        raise ValueError("Unexpected benchmark size or provider invocation")
    report = dict(source=str(args.data), source_sha256=file_sha256(args.data), output=str(output), seed=args.seed,
                  threshold=threshold, rows=len(data), cross_partition_rows_reassigned=changed,
                  manifest_hash=manifest["hash"], splits=manifest["splits"], candidates=candidates, selected_model=winner,
                  benchmark_cases=args.cases, benchmark_language=args.benchmark_language, benchmark=measured, activated=False,
                  training_mode=args.training_mode, extra_test_rows_reserved_before_training=reserved_rows,
                  sample_distribution=selected.groupby(["lang", "label"]).size().reset_index(name="count").to_dict("records"),
                  original_sample_rows=int(selected.generation_method.eq("original_corrected").sum()),
                  unique_sample_families=int(selected.group_id.nunique()),
                  standalone_ml=metrics(selected.label.to_numpy(int), results.standalone_ml_probability.to_numpy(), threshold),
                  limitations=["Labels are rule-audited, not individually human-certified.",
                               "Synthetic templates may inflate generalization estimates.",
                               "No LLM, MCP, scope or Output Guard generation was evaluated; token consumption is zero.",
                               "Results are not directly comparable to the previous corpus with different labels and sampling."])
    if args.activate:
        backup = preserve_records(config)
        processed = Path(config["paths"]["processed_data"])
        for filename in ("training_data.csv", "split_manifest.json"):
            existing = processed / filename
            if existing.exists():
                shutil.copy2(existing, backup / filename)
        for p in (ROOT / "config/config.yaml", ROOT / "promption/resources/config.yaml"):
            shutil.copy2(p, backup / (p.parent.name + "-config.yaml"))
        reviewed = processed / "reviewed_training_data.csv"
        if reviewed.exists():
            shutil.copy2(reviewed, backup / reviewed.name)
        shutil.copy2(output / "training_data.csv", reviewed)
        shutil.copy2(output / "training_data.csv", processed / "training_data.csv")
        shutil.copy2(output / "split_manifest.json", processed / "split_manifest.json")
        active = Path(config["model"]["lightweight_classifier_path"])
        chosen = Path(candidates[winner]["model_path"])
        shutil.copy2(chosen, active)
        shutil.copy2(chosen.with_suffix(".metadata.json"), active.with_suffix(".metadata.json"))
        for p in (ROOT / "config/config.yaml", ROOT / "promption/resources/config.yaml"):
            replace_path(p, "reviewed_dataset", reviewed.relative_to(ROOT).as_posix())
        pd.DataFrame([candidates[winner]["test"]["all/all"]]).to_csv(Path(config["paths"]["results"]) / "model_metrics_tfidf.csv", index=False)
        shutil.copy2(Path(config["paths"]["results"]) / "model_metrics_tfidf.csv", Path(config["paths"]["results"]) / "model_metrics.csv")
        report.update(activated=True, backup=str(backup))
    (output / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    selection = "Modelo preseleccionado en la comparación anterior" if args.training_mode == "bilingual" else "Modelo seleccionado por validación"
    lines = ["# Comparación de entrenamiento corregido", "", f"{selection}: **{winner}**. Umbral {threshold}; semilla {args.seed}.", "",
             "| Entrenamiento | Idioma de prueba | Recall | FPR | F1 |", "|---|---|---:|---:|---:|"]
    for name, details in candidates.items():
        for lang in ("es", "en"):
            m = details["test"][f"{lang}/all"]
            lines.append(f"| {name} | {lang} | {m['recall']:.2%} | {m['FPR']:.2%} | {m['f1']:.2%} |")
    lines += ["", f"Benchmark: {args.cases} casos reservados ({args.benchmark_language}), equilibrados y aleatorios.",
              f"TP={measured['tp']}; FP={measured['fp']}; FN={measured['fn']}; TN={measured['tn']}.",
              "", *report["limitations"]]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(dict(output=str(output), selected_model=winner, activated=report["activated"],
                          benchmark={key: measured[key] for key in ("tp", "fp", "fn", "tn", "recall", "fpr", "latency")}), indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
