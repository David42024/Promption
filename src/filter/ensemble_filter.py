"""Ensemble filter — orchestrates input detection and guarded generation."""
from dataclasses import dataclass

from src.filter.heuristic_filter import HeuristicFilter, HeuristicResult
from src.filter.ml_filter import MLFilter, MLResult
from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config()
_MODEL_CONF = _CONF.get("model", {})
_USE_LIGHTWEIGHT = _MODEL_CONF.get("use_lightweight_ml", False)

logger.info("ML backend: %s", "lightweight" if _USE_LIGHTWEIGHT else "embeddings")


def risk_band(score: float, low_threshold: float = 0.33,
              high_threshold: float = 0.66) -> str:
    """Return LOW, MEDIUM or HIGH using inclusive middle-band boundaries."""
    if score < low_threshold:
        return "LOW"
    if score <= high_threshold:
        return "MEDIUM"
    return "HIGH"


def decide_pipeline_action(heuristic_score: float, ml_probability: float | None,
                           low_threshold: float = 0.33,
                           high_threshold: float = 0.66) -> str:
    """Apply the explicit ALLOWED/GUARDED/BLOCKED decision matrix."""
    if heuristic_score <= 0.0:
        return "ALLOWED"
    if heuristic_score >= 1.0:
        return "BLOCKED"
    if ml_probability is None:
        return "GUARDED"
    heuristic_band = risk_band(heuristic_score, low_threshold, high_threshold)
    ml_band = risk_band(ml_probability, low_threshold, high_threshold)
    if heuristic_band == "LOW" and ml_band == "LOW":
        return "ALLOWED"
    if heuristic_band in {"MEDIUM", "HIGH"} and ml_band == "HIGH":
        return "BLOCKED"
    return "GUARDED"

# Import lightweight ML filter if enabled
if _USE_LIGHTWEIGHT:
    from src.filter.ml_filter_lightweight import LightMLFilter
    logger.info("DEBUG: Using LightMLFilter (TF-IDF + LogisticRegression)")
else:
    logger.info("DEBUG: Using regular MLFilter (SentenceTransformers + RandomForest)")


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
        if self.decision == "GUARDED":
            ml_probability = self.ml.probability if self.ml is not None else None
            ml_text = "no disponible" if ml_probability is None else f"{ml_probability:.2f}"
            return f"requiere Output Guard (heurística={self.heuristic.score:.2f}, ML={ml_text})"
        reasons = []
        if self.heuristic.blocked:
            rules = ", ".join(r["name"] for r in self.heuristic.matched_rules[:3])
            reasons.append(f"heurística ({rules or 'score alto'})")
        if self.ml is not None and self.ml.blocked:
            reasons.append(f"ML (p={self.ml.probability:.2f})")
        return " + ".join(reasons) or "permitido"

    @property
    def requires_output_guard(self) -> bool:
        return self.decision == "GUARDED"


class EnsembleFilter:
    def __init__(self, heuristic: HeuristicFilter | None = None, ml: MLFilter | None = None,
                 ml_threshold: float | None = None):
        conf = _CONF.get("ensemble", {})
        self.heuristic_weight = float(conf.get("heuristic_weight", 0.4))
        self.ml_weight = float(conf.get("ml_weight", 0.6))
        self.final_threshold = float(conf.get("final_threshold", 0.5))
        self.low_threshold = float(conf.get("decision_low_threshold", 0.33))
        self.high_threshold = float(
            ml_threshold if ml_threshold is not None else conf.get("decision_high_threshold", 0.66)
        )
        if not 0.0 < self.low_threshold < self.high_threshold < 1.0:
            raise ValueError("Decision thresholds must satisfy 0 < low < high < 1")
        self.heuristic = heuristic or HeuristicFilter()
        
        # Use lightweight ML if configured, otherwise use regular ML
        if _USE_LIGHTWEIGHT:
            self.ml = ml or LightMLFilter()
        else:
            self.ml = ml or MLFilter()
        self.ml_threshold = self.high_threshold

    def analyze(self, text: str, use_ml: bool = True, roles: list[str] | None = None) -> EnsembleResult:
        import time

        start = time.perf_counter()
        t_heur0 = time.perf_counter()
        heur = self.heuristic.analyze(text, roles=roles)
        heuristic_latency = (time.perf_counter() - t_heur0) * 1000

        ml_res: MLResult | None = None
        ml_latency = 0.0
        use_ml = use_ml and self.ml.is_trained()
        if use_ml:
            t_ml0 = time.perf_counter()
            try:
                ml_res = self.ml.analyze(text)
                ml_res.threshold = self.high_threshold
                ml_res.blocked = ml_res.probability > self.high_threshold
            except Exception:
                ml_res = None
            ml_latency = (time.perf_counter() - t_ml0) * 1000

        heuristic_risk = heur.score if heur.signal == "malicious" else 0.0
        ml_probability = ml_res.probability if ml_res is not None else None
        score = (
            self.heuristic_weight * heuristic_risk + self.ml_weight * ml_probability
            if ml_probability is not None else heuristic_risk
        )
        explicit_benign_override = heur.signal == "benign"
        decision = decide_pipeline_action(
            heur.score,
            ml_probability,
            self.low_threshold,
            self.high_threshold,
        )
        if explicit_benign_override:
            score = 0.0
            if ml_res is not None:
                ml_res.blocked = False
        blocked = decision == "BLOCKED"
        safe_intent_override = False

        merged = {
            "heuristic_score": heur.score,
            "heuristic_signal": heur.signal,
            "heuristic_risk_contribution": heuristic_risk,
            "ml_probability": ml_res.probability if ml_res else None,
            "benign_matched": list(heur.benign_matched),
            "ensemble_score": score,
            "matched_rules": [r["name"] for r in heur.matched_rules],
            "ml_available": ml_res is not None,
            "safe_intent_override": safe_intent_override,
            "explicit_benign_override": explicit_benign_override,
            "requires_output_guard": decision == "GUARDED",
            "heuristic_band": risk_band(heur.score, self.low_threshold, self.high_threshold),
            "ml_band": (
                risk_band(ml_probability, self.low_threshold, self.high_threshold)
                if ml_probability is not None else "UNAVAILABLE"
            ),
            "decision_low_threshold": self.low_threshold,
            "decision_high_threshold": self.high_threshold,
        }
        latency_ms = (time.perf_counter() - start) * 1000
        return EnsembleResult(
            blocked=blocked,
            decision=decision,
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
            "ml_threshold": self.high_threshold,
            "decision_low_threshold": self.low_threshold,
            "decision_high_threshold": self.high_threshold,
        }


def build_default() -> EnsembleFilter:
    return EnsembleFilter()
