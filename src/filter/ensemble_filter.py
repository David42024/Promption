"""Ensemble filter — orchestrates heuristic + ML layers.

Decision strategy (default OR):
    score = heuristic_weight * heuristic_score + ml_weight * ml_probability
    blocked = heuristic.blocked OR ml.blocked OR score >= final_threshold

The OR logic keeps the system safe (fail-safe): any layer flagging is enough.
"""
from dataclasses import dataclass

from src.filter.heuristic_filter import HeuristicFilter, HeuristicResult
from src.filter.ml_filter import MLFilter, MLResult
from src.utils.config import load_config

_CONF = load_config().get("ensemble", {})


@dataclass
class EnsembleResult:
    blocked: bool
    decision: str
    score: float
    heuristic: HeuristicResult
    ml: MLResult | None
    merged_features: dict
    latency_ms: float
    layer: str = "ensemble"
    heuristic_latency_ms: float = 0.0
    ml_latency_ms: float = 0.0

    @property
    def blocking_reason(self) -> str:
        reasons = []
        if self.heuristic.blocked:
            rules = ", ".join(r["name"] for r in self.heuristic.matched_rules[:3])
            reasons.append(f"heurística ({rules or 'score alto'})")
        if self.ml is not None and self.ml.blocked:
            reasons.append(f"ML (p={self.ml.probability:.2f})")
        return " + ".join(reasons) or "permitido"


class EnsembleFilter:
    def __init__(self, heuristic: HeuristicFilter | None = None, ml: MLFilter | None = None):
        conf = _CONF
        self.heuristic_weight = float(conf.get("heuristic_weight", 0.4))
        self.ml_weight = float(conf.get("ml_weight", 0.6))
        self.final_threshold = float(conf.get("final_threshold", 0.5))
        self.heuristic = heuristic or HeuristicFilter()
        self.ml = ml or MLFilter()

    def analyze(self, text: str, use_ml: bool = True) -> EnsembleResult:
        import time

        start = time.perf_counter()
        t_heur0 = time.perf_counter()
        heur = self.heuristic.analyze(text)
        heuristic_latency = (time.perf_counter() - t_heur0) * 1000

        ml_res: MLResult | None = None
        ml_latency = 0.0
        use_ml = use_ml and self.ml.is_trained()
        if use_ml:
            t_ml0 = time.perf_counter()
            try:
                ml_res = self.ml.analyze(text)
            except Exception:
                ml_res = None
            ml_latency = (time.perf_counter() - t_ml0) * 1000

        if ml_res is not None:
            score = self.heuristic_weight * heur.score + self.ml_weight * ml_res.probability
            blocked = heur.blocked or ml_res.blocked or score >= self.final_threshold
        else:
            score = heur.score
            blocked = heur.blocked

        merged = {
            "heuristic_score": heur.score,
            "ml_probability": ml_res.probability if ml_res else None,
            "ensemble_score": score,
            "matched_rules": [r["name"] for r in heur.matched_rules],
            "ml_available": ml_res is not None,
        }
        latency_ms = (time.perf_counter() - start) * 1000
        return EnsembleResult(
            blocked=blocked,
            decision="BLOCKED" if blocked else "ALLOWED",
            score=score,
            heuristic=heur,
            ml=ml_res,
            merged_features=merged,
            latency_ms=latency_ms,
            heuristic_latency_ms=heuristic_latency,
            ml_latency_ms=ml_latency,
        )

    def layers_status(self) -> dict:
        return {
            "heuristic_rules": len(self.heuristic._rules),
            "ml_trained": self.ml.is_trained(),
            "ml_loaded": self.ml.is_loaded,
        }


def build_default() -> EnsembleFilter:
    return EnsembleFilter()