"""Tests for the fail-safe three-state security classification."""

from src.api.classification import (
    BENIGN,
    MALICIOUS,
    UNCERTAIN,
    classify_security_result,
)


def test_blocked_result_is_malicious():
    assert classify_security_result(
        blocked=True,
        ml_probability=0.9,
    ) == (MALICIOUS, False)


def test_low_risk_result_is_benign():
    assert classify_security_result(
        blocked=False,
        ml_probability=0.19,
    ) == (BENIGN, False)


def test_intermediate_result_requires_review():
    assert classify_security_result(
        blocked=False,
        ml_probability=0.54,
    ) == (UNCERTAIN, True)


def test_missing_ml_requires_review_even_with_low_score():
    assert classify_security_result(
        blocked=False,
        ml_probability=None,
    ) == (UNCERTAIN, True)


def test_benign_threshold_boundary_is_uncertain():
    assert classify_security_result(
        blocked=False,
        ml_probability=0.4,
    ) == (UNCERTAIN, True)


def test_malicious_threshold_boundary_is_malicious():
    assert classify_security_result(
        blocked=False,
        ml_probability=0.6,
    ) == (MALICIOUS, False)
