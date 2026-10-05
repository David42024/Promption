"""Training, artifact identity and preservation follow the selected backend."""
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from promption.training.artifacts import file_sha256, model_provenance, preserve_records, selected_backend
from promption.training.split import stratified_split


def config_at(root):
    return {"model": {"use_lightweight_ml": True,
                      "classifier_path": str(root / "models/random_forest.pkl"),
                      "lightweight_classifier_path": str(root / "models/lightweight_classifier.pkl")},
            "paths": {"results": str(root / "results"), "plots": str(root / "results/plots")}}


def test_preservation_keeps_models_metrics_and_unknown_benchmark_provenance(tmp_path):
    config = config_at(tmp_path)
    for relative in ("models/random_forest.pkl", "models/lightweight_classifier.pkl",
                     "results/model_metrics.csv", "results/benchmark_results.csv", "results/plots/confusion.png"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative.encode())
    backup = preserve_records(config)
    records = json.loads((backup / "manifest.json").read_text())["files"]
    assert len(records) == 5
    assert (backup / "models/random_forest.pkl").read_bytes() == b"models/random_forest.pkl"
    assert (backup / "results/model_metrics.csv").read_bytes() == b"results/model_metrics.csv"
    for entry in records:
        assert file_sha256(backup / entry["file"]) == entry["sha256"]
    assert preserve_records(config) != backup


def test_provenance_does_not_attach_stale_training_metadata(tmp_path):
    path = tmp_path / "model.pkl"
    path.write_bytes(b"new model")
    path.with_suffix(".metadata.json").write_text(json.dumps({"sha256": "old", "backend": "other"}))
    result = model_provenance(path, "tfidf_logistic_regression")
    assert result["sha256"] == file_sha256(path)
    assert "training" not in result


def test_split_maps_filtered_indices_back_to_original_rows():
    df = pd.DataFrame({"source": ["synth_v2", "public", "synth_v2", "public", "public", "public"],
                       "label": [1, 0, 1, 1, 0, 1], "lang": ["es"] * 6})
    indices = stratified_split(df)
    assert set(indices).issubset({1, 3, 4, 5})
    assert set(df.iloc[indices]["label"]) == {0, 1}


def test_benchmark_trains_configured_tfidf_artifact(monkeypatch, tmp_path):
    import sys
    from scripts import run_benchmark
    from promption.training import train_lightweight
    config = config_at(tmp_path)
    calls = []
    monkeypatch.setattr(run_benchmark, "selected_backend", lambda: selected_backend(config))
    monkeypatch.setattr(run_benchmark, "preserve_records", lambda: tmp_path)
    monkeypatch.setattr(run_benchmark.dataset_mod, "prepare_training_data", lambda: None)
    monkeypatch.setattr(train_lightweight, "train", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(sys, "argv", ["run_benchmark", "--train-only"])
    run_benchmark.main()
    assert calls == [{"out_path": tmp_path / "models/lightweight_classifier.pkl", "preserve": False}]


def test_no_train_uses_existing_selected_model(monkeypatch, tmp_path):
    import sys
    from scripts import run_benchmark
    config = config_at(tmp_path)
    backend, path = selected_backend(config)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"trained")
    loaded = []
    monkeypatch.setattr(run_benchmark, "selected_backend", lambda: (backend, path))
    monkeypatch.setattr(run_benchmark, "preserve_records", lambda: tmp_path)
    monkeypatch.setattr(run_benchmark.dataset_mod, "prepare_training_data", lambda: None)
    ensemble = SimpleNamespace(ml=SimpleNamespace(_ensure_loaded=lambda: loaded.append(True)))
    monkeypatch.setattr(run_benchmark, "build_default", lambda: ensemble)
    class Runner:
        def __init__(self, filter, opts):
            assert filter is ensemble and not opts.use_llm
        def run(self):
            return None, dict.fromkeys(["asr_without_filter", "asr_with_filter", "asr_reduction", "precision", "recall", "f1"], 0)
    monkeypatch.setattr(run_benchmark, "BenchmarkRunner", Runner)
    monkeypatch.setattr(sys, "argv", ["run_benchmark", "--no-train", "--no-llm"])
    run_benchmark.main()
    assert loaded == [True]


def test_direct_random_forest_training_preserves_previous_artifacts(monkeypatch, tmp_path):
    import numpy as np
    from promption.training import train as forest
    from promption.utils import visualizer
    config = config_at(tmp_path)
    config["model"].update(embedding_model="test-encoder", n_trees=4, max_depth=3,
                           min_samples_leaf=1, random_state=42)
    config["paths"].update(classifier=config["model"]["classifier_path"],
                           raw_data=str(tmp_path / "data/raw"))
    old_model = Path(config["model"]["classifier_path"])
    old_model.parent.mkdir(parents=True)
    old_model.write_bytes(b"previous random forest")
    old_metrics = tmp_path / "results/model_metrics.csv"
    old_metrics.parent.mkdir(parents=True)
    old_metrics.write_text("previous metrics", encoding="utf-8")
    df = pd.DataFrame({"prompt": [f"example {i}" for i in range(20)],
                       "label": [0, 1] * 10, "lang": ["en"] * 20,
                       "source": ["public"] * 20})
    monkeypatch.setattr(forest, "_CONF", config)
    monkeypatch.setattr(forest, "load_config", lambda: config)
    monkeypatch.setattr(forest, "load_training_data", lambda: df)
    monkeypatch.setattr(forest, "embed_dataset", lambda frame, model, cache: np.asarray(
        [[i % 2, i / 20] for i in range(len(frame))], dtype=float))
    monkeypatch.setattr(forest, "preserve_records", lambda: preserve_records(config))
    monkeypatch.setattr(visualizer, "plot_confusion_matrix", lambda *args: None)
    monkeypatch.setattr(visualizer, "plot_feature_importance", lambda *args: None)
    forest.main()
    backups = list((tmp_path / "results/backups").glob("pre_run_*"))
    assert len(backups) == 1
    assert (backups[0] / "models/random_forest.pkl").read_bytes() == b"previous random forest"
    assert (backups[0] / "results/model_metrics.csv").read_text() == "previous metrics"
    assert old_metrics.read_text() == "previous metrics"
    assert model_provenance(old_model, "embeddings_random_forest")["training"]["embedding_model"] == "test-encoder"
    assert (tmp_path / "results/model_metrics_embeddings_random_forest.csv").is_file()
