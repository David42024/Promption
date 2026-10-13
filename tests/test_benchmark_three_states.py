"""Offline regressions: preserve input state and fail closed on ambiguous scope.

Run: PYTHONPATH=. pytest -q tests/test_benchmark_three_states.py
"""
from types import SimpleNamespace

import pandas as pd
import pytest

from promption.benchmark.metrics import three_state_metrics
from promption.benchmark.runner import BenchmarkRunner, RunnerOptions
from promption.filter.ensemble_filter import EnsembleResult
from promption.filter.heuristic_filter import HeuristicResult


class OfflineFilter:
    ml = SimpleNamespace(model_path=None)

    def analyze(self, prompt, use_ml=True):
        state = prompt.split(" ", 1)[0]
        assert state in {"BLOCKED", "GUARDED", "ALLOWED"}
        heur = HeuristicResult(blocked=state == "BLOCKED", score=1.0 if state == "BLOCKED" else 0.5)
        return EnsembleResult(
            blocked=state == "BLOCKED", decision=state,
            score=1.0 if state == "BLOCKED" else 0.5,
            heuristic=heur, ml=None, merged_features={}, latency_ms=0.01,
        )


class NeverCallLLM:
    model = "offline-fake"

    def health(self):
        return {"connected": True}

    def generate(self, *args, **kwargs):
        raise AssertionError("Scope not authorized; LLM must not be called")


def benchmark_data():
    return pd.DataFrame([
        {"prompt": "BLOCKED ataque", "label": 1, "dataset": "test", "attack_type": "injection", "source": "test"},
        {"prompt": "GUARDED ataque", "label": 1, "dataset": "test", "attack_type": "injection", "source": "test"},
        {"prompt": "ALLOWED benigno", "label": 0, "dataset": "test", "attack_type": "benign", "source": "test"},
    ])


def test_runner_exposes_three_states_and_binary_compatibility():
    out, stats = BenchmarkRunner(
        filter=OfflineFilter(), ollama=NeverCallLLM(),
        opts=RunnerOptions(data=benchmark_data(), use_llm=False, save=False),
    ).run()
    assert out["ensemble_decision"].tolist() == ["BLOCKED", "GUARDED", "ALLOWED"]
    assert out["policy_decision"].tolist() == ["BLOCKED", "GUARDED", "ALLOWED"]
    assert out["requires_output_guard"].tolist() == [False, True, False]
    assert out["filter_blocked"].tolist() == [1, 0, 0]
    assert out["response_delivered"].tolist() == [0, 0, 0]
    assert stats["layers"]["ensemble_three_state"]["attack_guarded"] == 1
    assert stats["layers"]["ensemble_three_state"]["attack_allowed"] == 0
    assert stats["layers"]["filter"]["fn"] == 1  # early-block only


def test_scope_failure_refuses_protected_generation():
    def faulty_scope(text, row):
        raise RuntimeError("indeterminate_scope")

    data = benchmark_data().iloc[[2]].reset_index(drop=True)
    out, _ = BenchmarkRunner(
        filter=OfflineFilter(), ollama=NeverCallLLM(),
        opts=RunnerOptions(data=data, use_llm=True, save=False, scope_evaluator=faulty_scope),
    ).run()
    record = out.iloc[0]
    assert record["ensemble_decision"] == "ALLOWED"
    assert record["scope_decision"] == "UNCERTAIN"
    assert record["policy_decision"] == "BLOCKED"
    assert record["final_blocked"] == 1
    assert record["generation_executed"] == 0
    assert record["response_delivered"] == 0


@pytest.mark.parametrize("value", ["UNKNOWN", "GUARDED", None, "invalid"])
def test_unrecognized_scope_verdicts_are_not_grants(value):
    data = benchmark_data().iloc[[2]].reset_index(drop=True)
    out, _ = BenchmarkRunner(
        filter=OfflineFilter(), ollama=NeverCallLLM(),
        opts=RunnerOptions(data=data, use_llm=True, save=False,
                           scope_evaluator=lambda prompt, row: {"decision": value}),
    ).run()
    assert out.iloc[0]["scope_decision"] == "UNCERTAIN"
    assert out.iloc[0]["policy_decision"] == "BLOCKED"
    assert out.iloc[0]["generation_executed"] == 0


def test_three_state_metrics_handles_missing_data_without_inventing_allows():
    df = pd.DataFrame({"label": [1, 1, 0, 0],
                       "ensemble_decision": ["BLOCKED", "GUARDED", "ALLOWED", None]})
    m = three_state_metrics(df)
    assert m["evaluated"] == 3 and m["skipped"] == 1
    assert m["counts"] == {"BLOCKED": 1, "GUARDED": 1, "ALLOWED": 1}
    assert m["attack_guarded"] == 1 and m["attack_allowed"] == 0


def test_missing_scope_decision_fails_closed():
    runner = BenchmarkRunner(filter=OfflineFilter(), ollama=NeverCallLLM(), opts=RunnerOptions(data=benchmark_data().iloc[[2]], use_llm=True, save=False, scope_evaluator=lambda prompt, row: {}))
    result, _ = runner.run()
    assert result.iloc[0]["scope_decision"] == "UNCERTAIN"
    assert result.iloc[0]["policy_decision"] == "BLOCKED"
    assert result.iloc[0]["generation_executed"] == 0
