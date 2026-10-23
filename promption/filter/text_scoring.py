"""Bounded whole-text and overlapping-window scoring for local classifiers."""
import numpy as np

from promption.filter.ml_filter import chunk_text
from promption.utils.text import normalize_content


def scoring_views(text: str, *, normalize: bool = False, chunk_chars: int | None = None,
                  chunk_overlap: int = 100) -> list[str]:
    if not isinstance(text, str) or type(normalize) is not bool:
        raise ValueError("Text and a boolean normalization flag are required")
    if chunk_chars is not None and (type(chunk_chars) is not int or chunk_chars < 1
                                    or type(chunk_overlap) is not int or not 0 <= chunk_overlap < chunk_chars):
        raise ValueError("Window size must be positive and overlap smaller than its size")
    text = normalize_content(text) if normalize else text
    return list(dict.fromkeys([text] + (chunk_text(text, chunk_chars, chunk_overlap)
                                      if chunk_chars is not None else [])))


def score_texts(vectorizer, classifier, texts: list[str], *, inference: dict | None = None,
                batch_size: int = 128) -> np.ndarray:
    """Keep the maximum risk from the complete input and every inspected window."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("Batch size must be a positive integer")
    positive = np.flatnonzero(np.asarray(classifier.classes_) == 1)
    if len(positive) != 1:
        raise ValueError("Classifier must expose exactly one positive class")
    result = np.zeros(len(texts), dtype=float)
    pending, owners = [], []

    def flush():
        probabilities = np.asarray(classifier.predict_proba(vectorizer.transform(pending)))
        if probabilities.ndim != 2 or probabilities.shape != (len(pending), len(classifier.classes_)):
            raise ValueError("Classifier returned invalid probability dimensions")
        probabilities = probabilities[:, positive[0]]
        if not np.all(np.isfinite(probabilities)) or np.any((probabilities < 0) | (probabilities > 1)):
            raise ValueError("Classifier probabilities must be finite and within [0, 1]")
        np.maximum.at(result, owners, probabilities)
        pending.clear()
        owners.clear()

    for index, text in enumerate(texts):
        for view in scoring_views(text, **(inference or {})):
            pending.append(view)
            owners.append(index)
            if len(pending) == batch_size:
                flush()
    if pending:
        flush()
    return result
