"""A benchmark must not silently retrain away an installed adapted detector."""
from pathlib import Path
import sys

import pytest

from scripts import run_benchmark


def test_default_benchmark_reuses_the_installed_model(monkeypatch, tmp_path):
    model = tmp_path / "model.pkl"
    model.write_bytes(b"installed adapted detector")
    (tmp_path / "training_data.csv").write_text("prompt,label\nhello,0\n")
    monkeypatch.setattr(sys, "argv", ["run_benchmark", "--no-llm"])
    monkeypatch.setattr(run_benchmark, "selected_backend", lambda: ("tfidf_logistic_regression", model))
    monkeypatch.setattr(run_benchmark, "load_config", lambda: {"paths": {"processed_data": str(tmp_path)}})
    monkeypatch.setattr(run_benchmark, "preserve_records", lambda: tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("An evaluation unexpectedly changed training data or retrained its model")
    monkeypatch.setattr(run_benchmark.dataset_mod, "prepare_training_data", forbidden)
    from promption.training import train_lightweight
    monkeypatch.setattr(train_lightweight, "train", forbidden)
    class StopAfterSelection(Exception):
        pass
    def selected():
        raise StopAfterSelection
    monkeypatch.setattr(run_benchmark, "build_default", selected)
    with pytest.raises(StopAfterSelection):
        run_benchmark.main()
    assert model.read_bytes() == b"installed adapted detector"


def test_conflicting_training_flags_fail_before_any_mutation(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_benchmark", "--no-train", "--retrain"])
    with pytest.raises(SystemExit) as error:
        run_benchmark.main()
    assert error.value.code == 2
