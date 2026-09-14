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
        score=0.9,
        ml_available=True,
        benign_threshold=0.3,
    ) == (MALICIOUS, False)


def test_low_risk_result_is_benign():
    assert classify_security_result(
        blocked=False,
        score=0.19,
        ml_available=True,
        benign_threshold=0.3,
    ) == (BENIGN, False)


def test_intermediate_result_requires_review():
    assert classify_security_result(
        blocked=False,
        score=0.31,
        ml_available=True,
        benign_threshold=0.3,
    ) == (UNCERTAIN, True)


def test_missing_ml_requires_review_even_with_low_score():
    assert classify_security_result(
        blocked=False,
        score=0.0,
        ml_available=False,
        benign_threshold=0.3,
    ) == (UNCERTAIN, True)


def test_threshold_boundary_is_benign():
    assert classify_security_result(
        blocked=False,
        score=0.3,
        ml_available=True,
        benign_threshold=0.3,
    ) == (BENIGN, False)
