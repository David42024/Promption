"""Verify the active local input-filter stack without calling an LLM provider."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from promption.filter.ensemble_filter import EnsembleFilter
from promption.filter.ml_filter_lightweight import LightMLFilter


EXPECTED_LIGHTWEIGHT_MODEL_SHA256 = "c4dfb0128d8aa6a91bbe0cc6e81b69b048ee2a1cc49bc072bf8eecc546299efb"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    filter_ = EnsembleFilter()
    if not isinstance(filter_.ml, LightMLFilter):
        raise RuntimeError(f"Expected LightMLFilter, got {type(filter_.ml).__name__}")
    model_path = filter_.ml.model_path.resolve()
    if sha256(model_path) != EXPECTED_LIGHTWEIGHT_MODEL_SHA256:
        raise RuntimeError("Active lightweight model hash differs from the published artifact")
    result = filter_.analyze("Explain the difference between IaaS and PaaS.")
    if result.merged_features["ml_status"] != "SUCCESS" or not result.merged_features["ml_available"]:
        raise RuntimeError("Active ML layer did not complete inference")
    print(json.dumps({
        "ml_class": type(filter_.ml).__name__,
        "model_path": str(model_path),
        "model_sha256": EXPECTED_LIGHTWEIGHT_MODEL_SHA256,
        "heuristic_rules": filter_.layers_status()["heuristic_rules"],
        "decision_low_threshold": filter_.low_threshold,
        "decision_high_threshold": filter_.high_threshold,
        "ml_status": result.merged_features["ml_status"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
