"""Interpret bounded analytical quotations as data while retaining raw evidence."""
from dataclasses import dataclass
import html
import re
import unicodedata


_QUOTES = re.compile(r'```[^\n`]*\n[\s\S]*?```|`[^`\n]+`|"[^"\n]+"|“[^”\n]+”|«[^»\n]+»|(?<!\w)\x27[^\x27\n]+\x27(?!\w)')
_ANALYSIS = re.compile(
    r'^[¿¡]?\s*(?:(?:please|por\s+favor)[,:]?\s+)?'
    r'(?:(?:(?:can|could|would|will)\s+you|(?:puedes|podr[ií]as|puede|podr[ií]a|quisiera))\s+'
    r'(?:(?:please|por\s+favor)\s+)?)?'
    r'(?:explain|analy[sz]e|translate|summari[sz]e|classify|describe|compare|proofread|'
    r'explica\w*|analiza\w*|traduc\w*|resume|resumir|clasifica\w*|describ\w*|compara\w*|corrige|corregir)\b'
    r'|^[¿¡]?\s*(?:what\s+does\s+QUOTED_DATA\s+mean|qu[eé]\s+significa\s+QUOTED_DATA)\s*[?.!]*\s*$', re.I)
_OPERATION = re.compile(r'\b(?:ignore|disregard|reveal|dump|execute\w*|obey|follow|apply|run|override|ignora\w*|revela\w*|ejec[úu]t\w*|sigue\w*|siguelo|síguelo|obedece\w*|aplica\w*|hazlo|dame|mu[eé]stra\w*|imprime\w*|exporta\w*|descarga\w*|abre|lee|do\s+it)\b', re.I)
_ADOPTION = re.compile(r'\b(?:execute\w*|obey|follow|apply|run\s+(?:it|that|the)|do\s+it|ejec[úu]t\w*|sigue\w*|síguelo|obedece\w*|aplica\w*|hazlo)\b', re.I)
_NEGATION = re.compile(r"\b(?:(?:do|does|must|should|will)\s*not|don['’]t|never|no|sin|ni|not|nunca|jam[aá]s)\s*(?:(?:ever|nunca|jam[aá]s)\s+)?$", re.I)


def positive_operation(pattern, text):
    position = 0
    while (match := pattern.search(text, position)) is not None:
        prefix = text[max(0, match.start() - 50):match.start()]
        if not _NEGATION.search(prefix) or re.search(
                r"\b(?:not|no|never|nunca|jam[aá]s)\s*(?:not|no|never|nunca|jam[aá]s)\s*$", prefix, re.I):
            return True
        position = match.start() + 1
    return False


@dataclass(frozen=True)
class InputEvidence:
    instruction_text: str
    quoted_texts: tuple[str, ...] = ()
    origin: str = "user"

    def metadata(self):
        return {"origin": self.origin, "quoted_spans": len(self.quoted_texts),
                "interpretation": "analytical_data" if self.quoted_texts else "instructions_or_unresolved",
                "raw_evidence_retained": True}


def interpret_input(text: str, *, origin: str = "user") -> InputEvidence:
    text = html.unescape(unicodedata.normalize("NFKC", text))
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    if origin != "user" or len(text) > 20000:
        return InputEvidence(text, origin=origin)
    spans = list(_QUOTES.finditer(text))
    if not spans or len(spans) > 8 or any(len(s.group()) > 8192 for s in spans):
        return InputEvidence(text, origin=origin)
    frame = _QUOTES.sub(" QUOTED_DATA ", text)
    if (not _ANALYSIS.search(frame.strip()) or positive_operation(_OPERATION, frame)
            or re.search(r'[^\w\s.,:;?!¿¡()/-]', frame)):
        return InputEvidence(text, origin=origin)
    return InputEvidence(frame, tuple(s.group() for s in spans), origin)


def adopts_quoted_instructions(text: str) -> bool:
    return positive_operation(_ADOPTION, interpret_input(text).instruction_text)


_QUESTION = re.compile(r"^[¿]?\s*(?:what\s+(?:is|are|does)|who\s+(?:is|was)|how\s+(?:does|do|can)|"
    r"why\s+(?:is|are|does)|qu[eé]\s+(?:es|son|significa)|qui[eé]n\s+(?:es|fue)|"
    r"c[oó]mo\s+(?:funciona|se|puedo)|por\s+qu[eé])\b", re.I)
_REFERENCE = re.compile(r"\b(?:it|this|that|those|these|them|same|again|previous|above|earlier|"
    r"eso|esto|esa|ese|estos|esas|aquello|lo\s+(?:mismo|anterior)|antes|anterior\w*|repite|contin[uú]a|"
    r"system|developer|instructions?|prompt|secret\w*|password\w*|tokens?|credentials?|keys?|code|"
    r"sistema|instrucciones|secret\w*|contrase[ñn]as?|credenciales|clave\w*|c[oó]digo\w*|"
    r"intern\w*|private|hidden|ocult\w*|privad\w*)\b", re.I)


def self_contained_question(text: str) -> bool:
    """Recognize a narrow new-question frame for history isolation, never for authorization."""
    return (8 <= len(text) <= 500 and "\n" not in text and len(text.split()) >= 3
            and bool(_QUESTION.search(text)) and not _REFERENCE.search(text)
            and not _QUOTES.search(text) and not re.search(r"[;{}<>]", text))
