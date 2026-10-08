"""Ensemble filter — orchestrates input detection and guarded generation."""
import time
from dataclasses import dataclass

from promption.filter.exceptions import (
    MLError,
    MLInferenceError,
    MLModelLoadError,
    MLModelNotFoundError,
)
from promption.filter.heuristic_filter import HeuristicFilter, HeuristicResult
from promption.filter.ml_filter import MLFilter, MLResult
from promption.utils.config import load_config
from promption.utils.logger import logger

_CONF = load_config()
_MODEL_CONF = _CONF.get("model", {})
_USE_LIGHTWEIGHT = _MODEL_CONF.get("use_lightweight_ml", False)

logger.info("ML backend: %s", "lightweight" if _USE_LIGHTWEIGHT else "embeddings")


def risk_band(score: float, low_threshold: float = 0.33,
              high_threshold: float = 0.66) -> str:
    """Return LOW, MEDIUM or HIGH with the blocking boundary in HIGH."""
    if score < low_threshold:
        return "LOW"
    if score < high_threshold:
        return "MEDIUM"
    return "HIGH"


def decide_pipeline_action(heuristic_score: float, ml_probability: float | None,
                           low_threshold: float = 0.33,
                           high_threshold: float = 0.66,
                           heuristic_blocked: bool | None = None) -> str:
    """Block any evaluated veto and guard uncertain inputs."""
    if heuristic_blocked is None:
        heuristic_blocked = heuristic_score >= high_threshold
    if heuristic_blocked or (ml_probability is not None and ml_probability >= high_threshold):
        return "BLOCKED"
    if heuristic_score <= 0.0:
        return "ALLOWED"
    if ml_probability is None:
        return "GUARDED"
    heuristic_band = risk_band(heuristic_score, low_threshold, high_threshold)
    ml_band = risk_band(ml_probability, low_threshold, high_threshold)
    if heuristic_band == "LOW" and ml_band == "LOW":
        return "ALLOWED"
    return "GUARDED"


if _USE_LIGHTWEIGHT:
    from promption.filter.ml_filter_lightweight import LightMLFilter
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
        self.low_threshold = float(conf.get("decision_low_threshold", 0.33))
        self.high_threshold = float(
            ml_threshold if ml_threshold is not None else conf.get("decision_high_threshold", 0.66)
        )
        if not 0.0 < self.low_threshold < self.high_threshold < 1.0:
            raise ValueError("Decision thresholds must satisfy 0 < low < high < 1")
        self.heuristic = heuristic or HeuristicFilter()
        
        if _USE_LIGHTWEIGHT:
            self.ml = ml or LightMLFilter()
        else:
            self.ml = ml or MLFilter()
        self.ml_threshold = self.high_threshold

        # Observability state tracking
        self._ml_state: str = "HEALTHY" if self.ml.is_trained() else "UNAVAILABLE"
        self._ml_last_error_code: str | None = None
        self._consecutive_failures: int = 0
        self._alert_threshold: int = int(_CONF.get("limits", {}).get("ml_persistent_failure_threshold", 5))
        self._alert_triggered: bool = False

    def _record_ml_failure(self, error_code: str, error_type: str, new_state: str = "DEGRADED") -> None:
        self._ml_last_error_code = error_code
        self._consecutive_failures += 1
        previous_state = self._ml_state
        self._ml_state = new_state

        # State transition: emit sanitized log without raw prompt content
        if previous_state != new_state:
            logger.error(
                "ML filter state transitioned to %s (error_code=%s, error_type=%s)",
                new_state,
                error_code,
                error_type,
            )

        # Persistent failure condition
        if self._consecutive_failures >= self._alert_threshold and not self._alert_triggered:
            self._alert_triggered = True
            logger.warning(
                "ML persistent failure alert triggered (%d consecutive failures, error_code=%s, error_type=%s).",
                self._consecutive_failures,
                error_code,
                error_type,
            )
            conf = load_config()
            webhook = conf.get("alerts", {}).get("webhook_url")
            if webhook:
                logger.warning(
                    "External alert delivery not implemented. Receiver configured; alert recorded locally only."
                )
            else:
                logger.warning(
                    "No external alert receiver configured. Alert recorded locally only.",
                )

    def _record_ml_success(self) -> None:
        previous_failures = self._consecutive_failures
        previous_state = self._ml_state
        self._consecutive_failures = 0
        self._alert_triggered = False
        self._ml_state = "HEALTHY"
        self._ml_last_error_code = None

        if previous_state in ("DEGRADED", "UNAVAILABLE"):
            logger.info(
                "ML filter state recovered: transitioned from %s to HEALTHY after %d failure(s).",
                previous_state,
                previous_failures,
            )

    def analyze(self, text: str, use_ml: bool = True, roles: list[str] | None = None) -> EnsembleResult:
        start = time.perf_counter()
        t_heur0 = time.perf_counter()
        heur = self.heuristic.analyze(text, roles=roles)
        heuristic_latency = (time.perf_counter() - t_heur0) * 1000

        ml_res: MLResult | None = None
        ml_latency = 0.0
        ml_attempted = False
        ml_failed = False
        ml_status = "NOT_REQUESTED"
        ml_error_code: str | None = None

        explicit_benign_fast_path = heur.signal == "benign" and not heur.blocked

        if heur.blocked:
            ml_status = "SKIPPED_HEURISTIC_VETO"
        elif explicit_benign_fast_path:
            ml_status = "SKIPPED_BENIGN_FAST_PATH"
        elif not use_ml:
            ml_status = "SKIPPED_USER_DISABLED"
        elif not self.ml.is_trained():
            ml_status = "UNAVAILABLE_NOT_TRAINED"
            ml_error_code = "MODEL_NOT_FOUND"
            ml_failed = True
            self._record_ml_failure(ml_error_code, "ModelNotTrainedOrMissing", new_state="UNAVAILABLE")
        else:
            ml_attempted = True
            t_ml0 = time.perf_counter()
            try:
                ml_res = self.ml.analyze(text)
                ml_res.threshold = self.high_threshold
                ml_res.blocked = ml_res.probability >= self.high_threshold
                ml_status = "SUCCESS"
                self._record_ml_success()
            except MLModelNotFoundError as exc:
                ml_failed = True
                ml_status = "FAILED_MODEL_NOT_FOUND"
                ml_error_code = exc.code
                self._record_ml_failure(exc.code, type(exc).__name__, new_state="UNAVAILABLE")
            except MLModelLoadError as exc:
                ml_failed = True
                ml_status = "FAILED_LOAD_ERROR"
                ml_error_code = exc.code
                self._record_ml_failure(exc.code, type(exc).__name__, new_state="DEGRADED")
            except MLInferenceError as exc:
                ml_failed = True
                ml_status = "FAILED_INFERENCE_ERROR"
                ml_error_code = exc.code
                self._record_ml_failure(exc.code, type(exc).__name__, new_state="DEGRADED")
            except Exception as exc:
                ml_failed = True
                ml_status = "FAILED_UNKNOWN"
                ml_error_code = "UNKNOWN_ERROR"
                self._record_ml_failure("UNKNOWN_ERROR", type(exc).__name__, new_state="DEGRADED")
            finally:
                ml_latency = (time.perf_counter() - t_ml0) * 1000

        heuristic_risk = heur.score if heur.signal == "malicious" else 0.0
        ml_probability = ml_res.probability if ml_res is not None else None
        weighted_score = (
            self.heuristic_weight * heuristic_risk + self.ml_weight * ml_probability
            if ml_probability is not None else heuristic_risk
        )
        score = max(heuristic_risk, ml_probability or 0.0)

        # Fail-safe degradation decision
        if heur.blocked:
            decision = "BLOCKED"
        elif explicit_benign_fast_path:
            decision = "ALLOWED"
        elif ml_res is not None:
            decision = decide_pipeline_action(
                heur.score,
                ml_probability,
                self.low_threshold,
                self.high_threshold,
                heuristic_blocked=heur.blocked,
            )
        else:
            # ML unavailable or failed on uncertain input: fail-safe to GUARDED (requires Output Guard)
            decision = "GUARDED"

        blocked = decision == "BLOCKED"
        safe_intent_override = False

        merged = {
            "heuristic_score": heur.score,
            "heuristic_signal": heur.signal,
            "heuristic_risk_contribution": heuristic_risk,
            "ml_probability": ml_res.probability if ml_res else None,
            "benign_matched": list(heur.benign_matched),
            "ensemble_score": score,
            "weighted_score": weighted_score,
            "matched_rules": [r["name"] for r in heur.matched_rules],
            "ml_available": ml_res is not None,
            "ml_status": ml_status,
            "ml_error_code": ml_error_code,
            "ml_attempted": ml_attempted,
            "ml_failed": ml_failed,
            "ml_state": self._ml_state,
            "safe_intent_override": safe_intent_override,
            "explicit_benign_override": explicit_benign_fast_path,
            "benign_fast_path": explicit_benign_fast_path,
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
        trained = self.ml.is_trained()
        if not trained and self._ml_state != "UNAVAILABLE":
            self._record_ml_failure("MODEL_NOT_FOUND", "ModelNotTrainedOrMissing", new_state="UNAVAILABLE")
        elif trained and self._ml_state == "UNAVAILABLE":
            self._ml_state = "HEALTHY"
            self._ml_last_error_code = None
            self._consecutive_failures = 0
            self._alert_triggered = False
        return {
            "heuristic_rules": len(self.heuristic._rules),
            "ml_trained": trained,
            "ml_loaded": self.ml.is_loaded,
            "ml_state": self._ml_state,
            "ml_error_code": self._ml_last_error_code,
            "ml_consecutive_failures": self._consecutive_failures,
            "ml_threshold": self.high_threshold,
            "decision_low_threshold": self.low_threshold,
            "decision_high_threshold": self.high_threshold,
        }


def build_default() -> EnsembleFilter:
    return EnsembleFilter()
