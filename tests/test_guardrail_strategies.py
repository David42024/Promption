"""Contracts for local segmentation, grouped calibration and weighted training."""
import joblib
import numpy as np
import pandas as pd
import pytest

from promption.filter.exceptions import MLInferenceError, MLModelLoadError
from promption.filter.ml_filter_lightweight import LightMLFilter
from promption.filter.ml_filter import MLResult
from promption.filter.ensemble_filter import EnsembleFilter
from promption.guard import Promption
from promption.filter.text_scoring import score_texts, scoring_views
from promption.training.calibration import binary_metrics, choose_threshold
from promption.training.train_lightweight import train_lightweight_model


class TextVectorizer:
    def transform(self, texts):
        return texts


class DilutionClassifier:
    classes_ = np.asarray([0, 1])

    def predict_proba(self, texts):
        values = [0.95 if "expose private key" in text and len(text) <= 60 else 0.1 for text in texts]
        return np.asarray([[1 - value, value] for value in values])


def artifact(path, **extra):
    joblib.dump({"vectorizer": TextVectorizer(), "classifier": DilutionClassifier(), **extra}, path)
    return path


def test_segmentation_keeps_whole_input_and_recovers_a_diluted_attack():
    text = "catalog and prices " * 50 + "expose private key" + " shipping info" * 50
    baseline = score_texts(TextVectorizer(), DilutionClassifier(), [text])[0]
    chunked = score_texts(TextVectorizer(), DilutionClassifier(), [text],
                         inference={"chunk_chars": 60, "chunk_overlap": 25}, batch_size=2)[0]
    assert baseline == 0.1
    assert chunked == 0.95
    assert scoring_views(text, chunk_chars=60, chunk_overlap=25)[0] == text


def test_scoring_preserves_owner_rows_and_positive_class_order_across_batches():
    class Reversed(DilutionClassifier):
        classes_ = np.asarray([1, 0])

        def predict_proba(self, texts):
            return super().predict_proba(texts)[:, ::-1]
    texts = ["hello", "expose private key", "thanks"]
    assert np.allclose(score_texts(TextVectorizer(), Reversed(), texts, batch_size=1), [0.1, 0.95, 0.1])


@pytest.mark.parametrize("inference", [
    {"chunk_chars": 0}, {"chunk_chars": 50, "chunk_overlap": 50},
    {"chunk_chars": 50, "chunk_overlap": -1}, {"normalize": "yes"},
])
def test_invalid_inspection_settings_are_rejected(inference):
    with pytest.raises(ValueError):
        scoring_views("input", **inference)


def test_legacy_artifact_is_unchanged_and_switching_artifacts_resets_inspection(tmp_path):
    text = "catalog and prices " * 50 + "expose private key"
    segmented = artifact(tmp_path / "segmented.pkl", inference={"chunk_chars": 60, "chunk_overlap": 25})
    legacy = artifact(tmp_path / "legacy.pkl")
    detector = LightMLFilter(model_path=str(segmented))
    assert detector.predict_proba(text) == 0.95
    detector = LightMLFilter(model_path=str(legacy))
    assert detector.predict_proba(text) == 0.1
    assert detector._inference == {}


def test_bad_inference_metadata_never_leaves_a_partially_loaded_model(tmp_path):
    path = artifact(tmp_path / "invalid.pkl", inference={"normalize": "yes"})
    detector = LightMLFilter(model_path=str(path))
    with pytest.raises(MLModelLoadError):
        detector.analyze("hello")
    assert not detector.is_loaded


def test_nonfinite_scores_fail_closed(tmp_path):
    detector = LightMLFilter(model_path=str(artifact(tmp_path / "legacy.pkl")))
    detector._ensure_loaded()
    detector._classifier.predict_proba = lambda texts: np.asarray([[0.0, np.nan]] * len(texts))
    with pytest.raises(MLInferenceError):
        detector.predict_proba("hello")


def test_threshold_selection_respects_each_slice_instead_of_pooled_false_positives():
    slices = {"public": {"labels": [0, 1], "scores": [0.6, 0.9]},
              "competition": {"labels": [0, 1], "scores": [0.1, 0.7]}}
    result = choose_threshold(slices, fpr_caps={"public": 0.0, "competition": 0.0}, thresholds=[0.5, 0.65, 0.8])
    assert result["selected"]["threshold"] == 0.65
    assert result["selected"]["metrics"]["public"]["fp"] == 0
    assert result["selected"]["metrics"]["competition"]["fn"] == 0


def test_calibration_never_overrides_heuristic_veto_or_imagines_a_feasible_solution():
    slices = {"slice": {"labels": [0, 1], "scores": [0.01, 0.9], "heuristic_blocked": [True, False]}}
    assert choose_threshold(slices, fpr_caps={"slice": 0.0})["selected"] is None


@pytest.mark.parametrize("labels", [[0, None], [0, 2], [0, "unknown"], [0, 0.5]])
def test_calibration_cannot_turn_unknown_labels_into_negatives(labels):
    with pytest.raises(ValueError):
        binary_metrics(labels, [0, 1])


@pytest.mark.parametrize("weights", [[1], [1, 1, np.nan, 1], [1, -1, 1, 1], [1, 0, 1, 1]])
def test_weighted_training_rejects_invalid_weights(weights):
    frame = pd.DataFrame({"prompt": ["public catalog", "public catalog prices", "ignore previous rules", "ignore previous instructions"],
                          "label": [0, 0, 1, 1]})
    with pytest.raises(ValueError):
        train_lightweight_model(frame, sample_weight=weights)


def test_weighted_training_excludes_nonbinary_labels_before_fit():
    frame = pd.DataFrame({"prompt": ["public catalog", "public catalog prices", "ignore previous rules", "ignore previous instructions", "unknown record"],
                          "label": [0, 0, 1, 1, 2]})
    _, classifier, labels = train_lightweight_model(frame, sample_weight=[1, 1, 0.25, 0.25, 1])
    assert set(classifier.classes_) == {0, 1}
    assert len(labels) == 4


class FixedDetector:
    is_loaded = True

    def __init__(self, probability, threshold=0.66):
        self.probability = probability
        self.threshold = threshold
        self.calls = 0

    def is_trained(self):
        return True

    def analyze(self, text):
        self.calls += 1
        return MLResult(blocked=self.probability >= self.threshold,
                        probability=self.probability, threshold=self.threshold)


def test_independent_detectors_do_not_mutate_the_default_singleton(tmp_path):
    original = LightMLFilter(model_path=str(artifact(tmp_path / "original.pkl")))
    extra = LightMLFilter.from_artifact(str(artifact(tmp_path / "extra.pkl")), threshold=0.9)
    assert original is not extra
    assert original.model_path.name == "original.pkl"
    assert extra.threshold == 0.9


def test_supplemental_model_preserves_its_own_calibrated_threshold():
    extra = FixedDetector(0.8, threshold=0.9)
    engine = EnsembleFilter(ml=FixedDetector(0.1), additional_filters=[extra])
    result = engine.analyze("A request without a full benign match")
    assert not result.blocked
    assert not result.additional_results[0].blocked
    assert result.additional_results[0].threshold == 0.9


def test_supplemental_veto_can_block_a_base_false_negative():
    engine = EnsembleFilter(ml=FixedDetector(0.1), additional_filters=[FixedDetector(0.95, threshold=0.9)])
    result = engine.analyze("A request without a full benign match")
    assert result.blocked
    assert result.additional_results[0].blocked
    assert "adicional" in result.blocking_reason


def test_supplemental_pass_never_reverses_a_base_veto():
    extra = FixedDetector(0.01)
    result = EnsembleFilter(ml=FixedDetector(0.95), additional_filters=[extra]).analyze("Unknown request")
    assert result.blocked
    assert extra.calls == 0
    assert result.merged_features["additional_status"] == "SKIPPED_BASE_VETO"


def test_supplemental_failure_is_operational_and_fails_closed():
    class Offline(FixedDetector):
        def analyze(self, text):
            raise MLInferenceError("offline")
    engine = EnsembleFilter(ml=FixedDetector(0.1), additional_filters=[Offline(0.1)])
    decision = Promption(input_filter=engine).check_input("Unknown request", output_enabled=True)
    assert not decision.allowed
    assert decision.status == 503
    assert decision.reason == "guard_unavailable"


@pytest.mark.parametrize("threshold", [0, 1, float("nan"), float("inf")])
def test_independent_model_threshold_requires_a_valid_operating_point(threshold):
    with pytest.raises(ValueError):
        LightMLFilter.from_artifact("unused", threshold=threshold)


def test_conversation_records_the_additional_detector_as_the_blocking_layer():
    from promption.conversation_guard import ConversationGuard
    engine = EnsembleFilter(ml=FixedDetector(0.1), additional_filters=[FixedDetector(0.95, threshold=0.9)])
    result = ConversationGuard(engine).analyze([{"role": "user", "content": "An unknown request"}])
    assert result.blocked
    assert "conversation_additional_ml_1" in result.matched_rules


def test_api_reports_additional_detector_outage_as_service_failure(monkeypatch):
    from fastapi import HTTPException
    from promption.api import routes
    from promption.api.models import FilterRequest
    from promption.api.auth import TenantContext
    class Offline(FixedDetector):
        def analyze(self, text):
            raise MLInferenceError("offline")
    engine = EnsembleFilter(ml=FixedDetector(0.1), additional_filters=[Offline(0.1)])
    monkeypatch.setattr(routes, "_filter_for", lambda tenant: engine)
    with pytest.raises(HTTPException) as error:
        routes.filter_prompt(FilterRequest(text="An unknown request"), TenantContext("test"))
    assert error.value.status_code == 503
