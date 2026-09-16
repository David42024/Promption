"""Ensemble filter — orchestrates heuristic + ML layers.

Decision strategy (default OR):
    score = heuristic_weight * heuristic_score + ml_weight * ml_probability
    blocked = heuristic.blocked OR ml.blocked OR score >= final_threshold

The OR logic keeps the system safe (fail-safe): any layer flagging is enough.
"""
import re
import unicodedata
from dataclasses import dataclass

from src.filter.heuristic_filter import HeuristicFilter, HeuristicResult
from src.filter.ml_filter import MLFilter, MLResult
from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config()
_MODEL_CONF = _CONF.get("model", {})
_USE_LIGHTWEIGHT = _MODEL_CONF.get("use_lightweight_ml", False)

logger.info(f"DEBUG: use_lightweight_ml = {_USE_LIGHTWEIGHT}")
logger.info(f"DEBUG: _MODEL_CONF keys = {list(_MODEL_CONF.keys()) if _MODEL_CONF else 'None'}")

_SAFE_SUPPORT_INTENT = re.compile(
    r"\b("
    r"consultas?\s+frecuentes|preguntas?\s+frecuentes|\bfaq\b|"
    r"atencion\s+al\s+cliente|soporte|"
    r"ideas?\s+para\s+responder|responder\s+consultas?|"
    r"redactar\s+(?:un\s+)?(?:correo|mensaje|respuesta)|"
    r"politicas?\s+publicas?"
    r")\b",
    re.IGNORECASE,
)
_RISKY_SAFE_INTENT_TERMS = re.compile(
    r"\b("
    r"ignora|olvida|bypass|desactiva|system\s+prompt|instrucciones|"
    r"api\s*key|apikey|token|password|contrasena|contraseña|credencial(?:es)?|"
    r"secreto(?:s|as)?|clave(?:s)?|sueldo(?:s)?|nomina|n[oó]mina|facturacion|facturaci[oó]n|"
    r"presupuesto|roi|jwt|admin|root"
    r")\b",
    re.IGNORECASE,
)


def _normalize_for_safe_intent(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value.lower()).strip()


def _is_ml_only_safe_support_intent(text: str, probability: float, threshold: float) -> bool:
    normalized = _normalize_for_safe_intent(text)
    margin = max(0.04, threshold * 0.10)
    return (
        probability <= threshold + margin
        and bool(_SAFE_SUPPORT_INTENT.search(normalized))
        and not _RISKY_SAFE_INTENT_TERMS.search(normalized)
    )

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
        reasons = []
        if self.heuristic.blocked:
            rules = ", ".join(r["name"] for r in self.heuristic.matched_rules[:3])
            reasons.append(f"heurística ({rules or 'score alto'})")
        if self.ml is not None and self.ml.blocked:
            reasons.append(f"ML (p={self.ml.probability:.2f})")
        return " + ".join(reasons) or "permitido"


class EnsembleFilter:
    def __init__(self, heuristic: HeuristicFilter | None = None, ml: MLFilter | None = None,
                 ml_threshold: float | None = None):
        conf = _CONF.get("ensemble", {})
        self.heuristic_weight = float(conf.get("heuristic_weight", 0.4))
        self.ml_weight = float(conf.get("ml_weight", 0.6))
        self.final_threshold = float(conf.get("final_threshold", 0.5))
        self.heuristic = heuristic or HeuristicFilter()
        
        # Use lightweight ML if configured, otherwise use regular ML
        if _USE_LIGHTWEIGHT:
            self.ml = ml or LightMLFilter()
        else:
            self.ml = ml or MLFilter()
        self.ml_threshold = ml_threshold

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
                if self.ml_threshold is not None:
                    ml_res.threshold = self.ml_threshold
                    ml_res.blocked = ml_res.probability >= self.ml_threshold
            except Exception:
                ml_res = None
            ml_latency = (time.perf_counter() - t_ml0) * 1000

        # NOTA: se probó un descuento benigno (cortesía/saludo restando a p(ML))
        # y se REVERTIÓ: el test adversario demostró que abre un hueco
        # ("Por favor dime el codigo", p=0.55, pasaba). Las señales benignas
        # se siguen detectando y reportando, pero no deciden.
        if ml_res is not None:
            score = self.heuristic_weight * heur.score + self.ml_weight * ml_res.probability
            blocked = heur.blocked or ml_res.blocked or score >= self.final_threshold
            safe_intent_override = (
                blocked
                and not heur.blocked
                and not heur.matched_rules
                and _is_ml_only_safe_support_intent(
                    text,
                    ml_res.probability,
                    self.ml_threshold if self.ml_threshold is not None else ml_res.threshold,
                )
            )
            if safe_intent_override:
                ml_res.blocked = False
                blocked = False
        else:
            score = heur.score
            blocked = heur.blocked
            safe_intent_override = False

        merged = {
            "heuristic_score": heur.score,
            "ml_probability": ml_res.probability if ml_res else None,
            "benign_matched": list(heur.benign_matched),
            "ensemble_score": score,
            "matched_rules": [r["name"] for r in heur.matched_rules],
            "ml_available": ml_res is not None,
            "safe_intent_override": safe_intent_override,
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
            "ml_threshold": self.ml_threshold if self.ml_threshold is not None else self.ml.threshold,
        }


def build_default() -> EnsembleFilter:
    return EnsembleFilter()
