"""Security classification for results produced by the attack filter."""

MALICIOUS = "MALICIOUS"
BENIGN = "BENIGN"
UNCERTAIN = "UNCERTAIN"


def classify_security_result(
    *,
    blocked: bool,
    ml_probability: float | None,
    benign_threshold: float = 0.33,
    malicious_threshold: float = 0.66,
    explicit_benign: bool = False,
    requires_output_guard: bool = False,
) -> tuple[str, bool]:
    """Map a binary filter result to a fail-safe three-state decision."""
    if blocked:
        return MALICIOUS, False
    if explicit_benign:
        return BENIGN, False
    if requires_output_guard:
        return UNCERTAIN, True
    if ml_probability is None:
        return UNCERTAIN, True
    if ml_probability < benign_threshold:
        return BENIGN, False
    if ml_probability < malicious_threshold:
        return UNCERTAIN, True
    return MALICIOUS, False
