"""Select an operating point on validation data with explicit false-positive caps."""
import numpy as np


def binary_metrics(labels, predictions) -> dict:
    labels, predictions = np.asarray(labels), np.asarray(predictions)
    if labels.ndim != 1 or predictions.shape != labels.shape or not len(labels):
        raise ValueError("Nonempty aligned binary observations are required")
    if not np.all(np.isin(labels, [0, 1])) or not np.all(np.isin(predictions, [0, 1])):
        raise ValueError("Unknown labels or decisions must be excluded explicitly")
    tp = int(np.sum((labels == 1) & (predictions == 1)))
    fp = int(np.sum((labels == 0) & (predictions == 1)))
    fn = int(np.sum((labels == 1) & (predictions == 0)))
    tn = int(np.sum((labels == 0) & (predictions == 0)))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": len(labels),
            "recall": tp / (tp + fn) if tp + fn else None,
            "fpr": fp / (fp + tn) if fp + tn else None,
            "precision": tp / (tp + fp) if tp + fp else 0.0}


def choose_threshold(slices: dict, *, fpr_caps: dict, thresholds=None) -> dict:
    """Maximize mean recall subject to every validation slice's false-positive budget."""
    if not slices or set(slices) != set(fpr_caps):
        raise ValueError("Each validation slice needs an explicit false-positive cap")
    if any(not np.isfinite(cap) or not 0 <= cap <= 1 for cap in fpr_caps.values()):
        raise ValueError("False-positive caps must be finite and within [0, 1]")
    grid = list(thresholds) if thresholds is not None else np.arange(0.34, 0.951, 0.01).round(2)
    if not len(grid) or any(not np.isfinite(value) or not 0 < value < 1 for value in grid):
        raise ValueError("Thresholds must be finite and strictly between zero and one")
    candidates = []
    for threshold in grid:
        metrics = {}
        for name, data in slices.items():
            probability = np.asarray(data["scores"], dtype=float)
            labels = np.asarray(data["labels"])
            if probability.shape != labels.shape or not np.all(np.isfinite(probability)):
                raise ValueError("Validation scores must be finite and aligned with labels")
            if np.any((probability < 0) | (probability > 1)):
                raise ValueError("Validation scores must be within [0, 1]")
            veto = np.asarray(data.get("heuristic_blocked", np.zeros(len(labels))), dtype=bool)
            benign = np.asarray(data.get("explicit_benign", np.zeros(len(labels))), dtype=bool)
            if veto.shape != labels.shape or benign.shape != labels.shape:
                raise ValueError("Heuristic decisions must align with validation labels")
            predictions = veto | (~benign & (probability >= threshold))
            metrics[name] = binary_metrics(labels, predictions)
            if metrics[name]["fpr"] is None or metrics[name]["recall"] is None:
                raise ValueError("Each validation slice needs both classes")
        feasible = all(metrics[name]["fpr"] <= fpr_caps[name] + 1e-12 for name in slices)
        candidates.append({"threshold": float(threshold), "feasible": feasible, "metrics": metrics,
                           "mean_recall": float(np.mean([value["recall"] for value in metrics.values()]))})
    feasible = [candidate for candidate in candidates if candidate["feasible"]]
    if not feasible:
        return {"selected": None, "candidates": candidates}
    selected = max(feasible, key=lambda candidate: (candidate["mean_recall"],
                   -sum(value["fp"] for value in candidate["metrics"].values()), candidate["threshold"]))
    return {"selected": selected, "candidates": candidates}
