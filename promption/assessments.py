"""Independent, non-authorizing security evaluations with bounded reason codes."""
from copy import deepcopy

CONTROLS = ("injection", "scope", "authorization")
STATES = frozenset({"allowed", "denied", "uncertain", "not_evaluated", "error"})


def empty_assessments():
    return {name: {"state": "not_evaluated", "reason": "not_evaluated", "source": name,
                   "evaluations": []} for name in CONTROLS}


def assess(assessments, control, state, reason, source):
    if control not in CONTROLS or state not in STATES:
        raise ValueError("Unknown assessment category")
    result = deepcopy(assessments or empty_assessments())
    item = {"state": state, "reason": reason, "source": source}
    result[control] = {**item, "evaluations": [*result[control]["evaluations"], item]}
    return result


def scope_assessments(decision, prior=None):
    result = deepcopy(prior or empty_assessments())
    if decision.status >= 500 or decision.reason == "scope_truncated":
        return assess(result, "scope", "error", decision.reason, "scope_evaluator")
    intent = decision.intent
    if intent is not None:
        result = assess(result, "injection", "allowed" if intent.attack == "none" else
                        "uncertain" if intent.attack == "unknown" else "denied",
                        "no_attack_detected" if intent.attack == "none" else intent.attack, "context_evaluator")
    return assess(result, "scope", "allowed" if decision.allowed else
                  "denied" if decision.classification == "OUT_OF_SCOPE" else "uncertain",
                  decision.reason, "scope_evaluator")


def merge_assessments(prior, current):
    result = deepcopy(prior or empty_assessments())
    for control, value in (current or {}).items():
        if control not in CONTROLS or value["state"] not in STATES:
            raise ValueError("Invalid assessment")
        if value["state"] == "not_evaluated":
            continue
        previous = result[control]
        result[control] = {**(previous if previous["state"] == "denied" else value),
                           "evaluations": [*previous["evaluations"], *value["evaluations"]]}
    return result
