"""Canonical intent metadata; external evidence never grants authority."""
from dataclasses import dataclass
import math

INTENTS = frozenset({"social", "public_information", "document_creation", "web_retrieval",
                    "clarification", "security_discussion", "protected_information",
                    "instruction_override", "privilege_escalation", "other", "unknown"})
ATTACKS = frozenset({"none", "instruction_override", "secret_extraction", "system_prompt_extraction",
                    "privilege_escalation", "indirect_injection", "unknown"})
RELATIONS = frozenset({"standalone", "follow_up", "quoted", "unresolved"})
ORIGINS = frozenset({"none", "user", "tool", "mixed"})


@dataclass(frozen=True)
class IntentAssessment:
    name: str
    attack: str
    relation: str
    origin: str
    confidence: float
    evidence: tuple[int, ...] = ()

    def to_dict(self):
        return {"name": self.name, "attack": self.attack, "relation": self.relation,
                "origin": self.origin, "confidence": self.confidence, "evidence": list(self.evidence)}


def validate_intent(value) -> IntentAssessment:
    if isinstance(value, IntentAssessment):
        value = value.to_dict()
    if not isinstance(value, dict):
        raise ValueError("A structured intent assessment is required")
    if (value.get("name") not in INTENTS or value.get("attack") not in ATTACKS
            or value.get("relation") not in RELATIONS or value.get("origin") not in ORIGINS):
        raise ValueError("Unknown intent category")
    confidence = value.get("confidence")
    evidence = value.get("evidence")
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence) or not 0 <= confidence <= 1
            or not isinstance(evidence, (list, tuple)) or len(evidence) > 8
            or any(type(index) is not int or not 0 <= index < 128 for index in evidence)
            or len(set(evidence)) != len(evidence)):
        raise ValueError("Invalid intent confidence or evidence")
    if value["attack"] == "none" and value["origin"] != "none":
        raise ValueError("A benign assessment cannot attribute an attack origin")
    if value["attack"] not in {"none", "unknown"} and value["origin"] == "none":
        raise ValueError("An attack requires its untrusted origin")
    return IntentAssessment(value["name"], value["attack"], value["relation"], value["origin"],
                            float(confidence), tuple(evidence))
