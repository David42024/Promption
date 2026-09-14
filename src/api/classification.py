"""Security classification for results produced by the attack filter."""

MALICIOUS = "MALICIOUS"
BENIGN = "BENIGN"
UNCERTAIN = "UNCERTAIN"


def classify_security_result(
    *,
    blocked: bool,
    score: float,
    ml_available: bool,
    benign_threshold: float,
) -> tuple[str, bool]:
    """Map a binary filter result to a fail-safe three-state decision."""
    if blocked:
        return MALICIOUS, False
    if not ml_available or score > benign_threshold:
        return UNCERTAIN, True
    return BENIGN, False
