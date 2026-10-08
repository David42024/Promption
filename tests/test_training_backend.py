"""Training, artifact identity and preservation follow the selected backend."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from promption.training.artifacts import file_sha256, model_provenance, preserve_records, selected_backend
from promption.training.split import create_splits


def config_at(root):
    return {"model": {"use_lightweight_ml": True,
                      "classifier_path": str(root / "models/random_forest.pkl"),
                      "lightweight_classifier_path": str(root / "models/lightweight_classifier.pkl")},
            "paths": {"results": str(root / "results"), "plots": str(root / "results/plots"), "processed_data": str(root / "processed")}}


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
    tr, val, te, ext = create_splits(df)
    all_idx = np.concatenate([tr, val, te, ext])
    assert set(all_idx).issubset(set(range(len(df))))
    assert len(all_idx) == len(set(all_idx)) == len(df)
    synth_indices = set(df[df["source"] == "synth_v2"].index)
    assert synth_indices.issubset(set(ext))


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
    assert (tmp_path / "results/model_metrics_embeddings_random_forest.csv").is_file()


def test_create_splits_has_zero_group_leakage():
    df = pd.DataFrame({
        "group_id": ["g1", "g1", "g2", "g3", "g4", "g4", "g5"],
        "source": ["translated_es", "public", "public", "public", "public", "public", "public"],
        "label": [1, 1, 0, 1, 0, 0, 1],
        "lang": ["es", "en", "en", "en", "en", "en", "en"]
    })
    tr, val, te, ext = create_splits(df)
    parts = {
        "train": set(df.iloc[tr]["group_id"]),
        "val": set(df.iloc[val]["group_id"]),
        "test": set(df.iloc[te]["group_id"]),
        "external": set(df.iloc[ext]["group_id"]),
    }
    # No group can be in more than one partition
    for p1 in parts:
        for p2 in parts:
            if p1 != p2:
                assert len(parts[p1] & parts[p2]) == 0, f"Overlap between {p1} and {p2}: {parts[p1] & parts[p2]}"
    # g1 has translated_es so all rows of g1 must be in external
    assert parts["external"] == {"g1"}


def test_payloads_requires_manifest_or_exploratory(tmp_path, monkeypatch):
    import pytest
    from promption.benchmark.payloads import load_evaluation_set
    monkeypatch.setattr("promption.benchmark.payloads.load_config", lambda: {
        "paths": {"processed_data": str(tmp_path / "nonexistent")},
        "model": {"lightweight_classifier_path": str(tmp_path / "model.pkl")}
    })
    monkeypatch.setattr("promption.benchmark.payloads.load_raw_data", lambda *args: pd.DataFrame({
        "prompt": ["hello"], "label": [0], "dataset": ["Benigno"], "attack_type": ["benign"], "source": ["local"], "group_id": ["g1"]
    }))
    monkeypatch.setattr("promption.benchmark.payloads.apply_quarantine", lambda df, *args: df)
    monkeypatch.setattr("promption.benchmark.payloads.apply_label_overrides", lambda df, *args: df)

    with pytest.raises(FileNotFoundError):
        load_evaluation_set()

    df_exp = load_evaluation_set(allow_exploratory=True)
    assert len(df_exp) == 1


def test_payloads_strict_metadata_verification(tmp_path, monkeypatch):
    import pytest
    from promption.benchmark.payloads import load_evaluation_set

    proc_dir = tmp_path / "proc"
    proc_dir.mkdir()
    manifest_file = proc_dir / "split_manifest.json"
    from promption.training.split import calculate_manifest_hash
    manifest_data = {
        "seed": 42,
        "splits": {"train": 0, "val": 0, "test": 1, "external": 0},
        "records": {"0": {"group_id": "g1", "source": "local", "partition": "test", "label": 0}}
    }
    canonical_hash = calculate_manifest_hash(manifest_data)
    manifest_data["hash"] = canonical_hash
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    model_path = tmp_path / "model.pkl"
    model_path.write_text("model bytes", encoding="utf-8")
    meta_path = tmp_path / "model.metadata.json"

    monkeypatch.setattr("promption.benchmark.payloads.load_config", lambda: {
        "paths": {"processed_data": str(proc_dir)},
        "model": {"use_lightweight_ml": True, "lightweight_classifier_path": str(model_path)}
    })
    monkeypatch.setattr("promption.benchmark.payloads.load_raw_data", lambda *args: pd.DataFrame({
        "prompt": ["hello"], "label": [0], "dataset": ["Benigno"], "attack_type": ["benign"], "source": ["local"], "group_id": ["g1"]
    }))
    monkeypatch.setattr("promption.benchmark.payloads.apply_quarantine", lambda df, *args: df)
    monkeypatch.setattr("promption.benchmark.payloads.apply_label_overrides", lambda df, *args: df)

    # 1. Metadata missing -> ValueError
    with pytest.raises(ValueError, match="no se encontraron metadatos"):
        load_evaluation_set(model_path=model_path)

    # 2. Metadata corrupt JSON -> ValueError
    meta_path.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(ValueError, match="metadatos corruptos o ilegibles"):
        load_evaluation_set(model_path=model_path)

    # 3. Metadata without manifest_hash -> ValueError
    meta_path.write_text(json.dumps({"some_key": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="no registra manifest_hash"):
        load_evaluation_set(model_path=model_path)

    # 4. Manifest hash mismatch -> ValueError
    meta_path.write_text(json.dumps({"manifest_hash": "different_hash"}), encoding="utf-8")
    with pytest.raises(ValueError, match="discrepancia entre el modelo"):
        load_evaluation_set(model_path=model_path)

    # 5. Matching canonical hash -> succeeds
    from promption.training.split import calculate_manifest_hash
    canonical_hash = calculate_manifest_hash(manifest_data)
    manifest_data["hash"] = canonical_hash
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
    meta_path.write_text(json.dumps({"manifest_hash": canonical_hash}), encoding="utf-8")
    df = load_evaluation_set(model_path=model_path)
    assert len(df) == 1

    # 6. Tampered manifest records retaining old declared hash -> ValueError
    tampered = dict(manifest_data)
    tampered["records"] = {
        "0": {"group_id": "g1", "partition": "train", "label": 1}
    }
    tampered["hash"] = canonical_hash  # retains previous hash
    manifest_file.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="ha sido alterado y no coincide con su hash"):
        load_evaluation_set(model_path=model_path)


def test_dataset_preserves_group_id_and_family_id(tmp_path, monkeypatch):
    from promption.training.dataset import load_raw_data

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    mal_file = raw_dir / "malicious_prompts.csv"
    ben_file = raw_dir / "benign_prompts.csv"

    # CSV with family_id and group_id
    mal_file.write_text(
        "prompt,dataset,attack_type,source,family_id,group_id\n"
        "test attack,OWASP,injection,translated,fam_01,grp_01\n",
        encoding="utf-8"
    )
    ben_file.write_text(
        "prompt,category,source,family_id,group_id\n"
        "test benign,general,local,fam_02,grp_02\n",
        encoding="utf-8"
    )

    df = load_raw_data(data_dir=str(raw_dir))
    assert "group_id" in df.columns
    assert "family_id" in df.columns
    # Group id resolves to family_id when provided
    assert df.loc[df["prompt"] == "test attack", "group_id"].iloc[0] == "fam_01"
    assert df.loc[df["prompt"] == "test attack", "family_id"].iloc[0] == "fam_01"
