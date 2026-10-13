"""The benchmark must count actual provider requests after a client retry."""
from types import SimpleNamespace
import pandas as pd
from promption.benchmark.runner import BenchmarkRunner, RunnerOptions
from promption.filter.ensemble_filter import EnsembleResult
from promption.filter.heuristic_filter import HeuristicResult
from promption.llm.ollama_client import LLMResponse


class PassFilter:
    ml = SimpleNamespace(model_path=None)
    def analyze(self, prompt, use_ml=True):
        return EnsembleResult(
            blocked=False, decision="GUARDED", score=0.5,
            heuristic=HeuristicResult(blocked=False, score=0.5),
            ml=None, merged_features={}, latency_ms=1.0,
        )


class RetriesOnce:
    model = "mock-provider"
    def health(self):
        return {"connected": True}
    def generate(self, prompt, system=None):
        return LLMResponse(
            text="Una respuesta pública normal", model=self.model, latency_ms=2.0,
            provider_calls=2, retry_count=1,
            input_tokens=22, output_tokens=35, total_tokens=57,
        )


def test_runner_accounts_provider_retries_and_does_not_invent_leaks():
    dataset = pd.DataFrame([
        {"prompt": "Explica computación en nube", "label": 0,
         "dataset": "Benigno", "attack_type": "benign", "source": "test"},
    ])
    out, metrics = BenchmarkRunner(
        filter=PassFilter(), ollama=RetriesOnce(),
        opts=RunnerOptions(data=dataset, use_llm=True, use_ml=False, save=False),
    ).run()
    assert int(out.iloc[0]["provider_calls"]) == 2
    assert int(out.iloc[0]["provider_retries"]) == 1
    assert metrics["tokens"]["attempted_calls"] == 2
    assert int(out.iloc[0]["response_delivered"]) == 1
    assert out.iloc[0]["ensemble_decision"] == "GUARDED"
