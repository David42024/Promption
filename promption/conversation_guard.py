"""Origin-aware inspection of cumulative user and tool instructions."""
from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass, field

from .utils.config import load_config, load_heuristics


class ConversationLimitError(ValueError):
    """The complete security context cannot be inspected within configured bounds."""


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str
    tool_name: str | None = None


@dataclass
class ConversationDecision:
    blocked: bool = False
    requires_output_guard: bool = False
    matched_rules: list[str] = field(default_factory=list)
    message_count: int = 0
    tool_message_count: int = 0
    reason: str = "conversation_checked"

    def metadata(self) -> dict:
        return {"blocked": self.blocked, "requires_output_guard": self.requires_output_guard,
                "matched_rules": self.matched_rules, "message_count": self.message_count,
                "tool_message_count": self.tool_message_count, "reason": self.reason}


def normalize_content(text: str) -> str:
    text = html.unescape(unicodedata.normalize("NFKC", text))
    text = "".join(character for character in text if unicodedata.category(character) != "Cf")
    return re.sub(r"\s+", " ", text).strip()


def _strings(value, depth: int = 0, *, include_keys: bool = False) -> list[str]:
    if depth > 12:
        raise ConversationLimitError("Structured tool result exceeds inspection depth")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item, depth + 1, include_keys=include_keys)]
    if isinstance(value, dict):
        return [text for key, item in value.items()
                for text in ([str(key)] if include_keys else []) + _strings(item, depth + 1, include_keys=include_keys)]
    return []


def message_text(message: ConversationMessage) -> str:
    if message.role == "tool":
        try:
            value = json.loads(message.content)
        except (ValueError, RecursionError):
            return normalize_content(message.content)
        return normalize_content(" ".join(_strings(value)))
    return normalize_content(message.content)


def validate_messages(messages: list, *, max_messages: int | None = None,
                      max_chars: int | None = None) -> list[ConversationMessage]:
    config = load_config().get("conversation_guard", {})
    max_messages = max_messages or int(config.get("max_messages", 128))
    max_chars = max_chars or int(config.get("max_chars", 100000))
    if not isinstance(messages, list) or len(messages) > max_messages:
        raise ConversationLimitError("Conversation exceeds message limit")
    result = []
    total = 0
    for message in messages:
        if isinstance(message, dict):
            message = ConversationMessage(**message)
        if not isinstance(message, ConversationMessage) or message.role not in {"user", "assistant", "tool"}:
            raise ValueError("Only user, assistant and tool evidence is accepted")
        if not isinstance(message.content, str):
            raise ValueError("Conversation content must be text")
        total += len(message.content)
        if total > max_chars:
            raise ConversationLimitError("Conversation exceeds character limit")
        result.append(message)
    return result


_ALIAS = re.compile(
    r"(?i)(?:\b(?:define|llama(?:remos)?|llamar[eé]|denomina|call|name)\s+[\"']?([\w-]{1,40})[\"']?\s+(?:a|al|como|as|to mean|=)\s+([^;\n]{1,200})"
    r"|[\"']?([\w-]{1,40})[\"']?\s+(?:significa|se refiere a|means|stands for)\s+([^;\n]{1,200})"
    r"|\b([A-Za-z][\w-]{0,39})\s*[:=]\s*([^;\n]{1,200}))"
)


def conversation_views(messages: list) -> list[str]:
    """Build separate and assembled views without promoting tool data to system text."""
    messages = validate_messages(messages)
    untrusted = [message for message in messages if message.role in {"user", "tool"}]
    texts = [message_text(message) for message in untrusted]
    texts = [text for text in texts if text]
    if not texts:
        return []
    aliases = {}
    expanded = []

    def expand(text):
        for _ in range(4):
            previous = text
            for alias, value in aliases.items():
                text = re.sub(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", lambda _: value,
                              text, flags=0 if len(alias) == 1 else re.IGNORECASE)
                if len(text) > 100000:
                    raise ConversationLimitError("Expanded conversation exceeds limit")
            if text == previous:
                return text
        raise ConversationLimitError("Conversation aliases cannot be resolved safely")

    for text in texts:
        definitions = list(_ALIAS.finditer(text))
        if definitions:
            for match in definitions:
                pairs = list(zip(match.groups()[::2], match.groups()[1::2]))
                alias, value = next(pair for pair in pairs if pair[0] is not None)
                if len(aliases) >= 32 and alias not in aliases:
                    raise ConversationLimitError("Too many conversation aliases")
                aliases[alias] = expand(value.strip(" .\"'"))
            expanded.append(text)
        else:
            expanded.append(expand(text))
    by_origin = [[message_text(message) for message in untrusted if message.role == role]
                 for role in ("user", "tool")]
    views = texts + [" ".join(texts), "".join(texts)] + [" ".join(part) for part in by_origin]
    if sum(map(len, expanded)) > int(load_config().get("conversation_guard", {}).get("max_chars", 100000)):
        raise ConversationLimitError("Expanded evidence exceeds character limit")
    views += expanded + [" ".join(expanded)]
    for message in untrusted:
        if message.role != "tool":
            continue
        views.append(normalize_content(message.content))
        try:
            value = json.loads(message.content)
        except (ValueError, RecursionError):
            continue
        views.append(normalize_content(" ".join(_strings(value, include_keys=True))))
    views += [re.sub(r"\s+", "", view) for view in list(views)]
    return list(dict.fromkeys(view for view in views if view))


class ConversationGuard:
    """Combine per-message, reconstructed and cumulative filter results with OR."""

    def __init__(self, input_filter=None):
        if input_filter is None:
            from .filter.ensemble_filter import EnsembleFilter
            input_filter = EnsembleFilter()
        self.input_filter = input_filter
        self.rules = [(rule["name"], re.compile(rule["pattern"], re.IGNORECASE | re.DOTALL))
                      for rule in load_heuristics().get("conversation_rules", [])
                      if rule.get("enabled", True)]

    def analyze(self, messages: list, *, roles: list[str] | None = None,
                use_ml: bool = True) -> ConversationDecision:
        messages = validate_messages(messages)
        decision = ConversationDecision(message_count=len(messages),
                                        tool_message_count=sum(message.role == "tool" for message in messages))
        views = conversation_views(messages)
        for text in views:
            heuristic = self.input_filter.heuristic.analyze(text, roles=roles)
            if heuristic.blocked:
                decision.blocked = True
                decision.matched_rules.extend(rule["name"] for rule in heuristic.matched_rules)
            for name, pattern in self.rules:
                if pattern.search(text):
                    decision.blocked = True
                    decision.matched_rules.append(name)
        if not decision.blocked and views:
            untrusted = [message for message in messages if message.role in {"user", "tool"}]
            combined = " ".join(message_text(message) for message in untrusted)
            result = self.input_filter.analyze(combined, roles=roles, use_ml=use_ml)
            decision.blocked |= result.blocked
            decision.requires_output_guard |= result.requires_output_guard
            if result.blocked:
                decision.matched_rules.extend(rule["name"] for rule in result.heuristic.matched_rules)
                if result.ml and result.ml.blocked:
                    decision.matched_rules.append("conversation_ml")
        decision.matched_rules = list(dict.fromkeys(decision.matched_rules))
        if decision.blocked:
            decision.reason = "conversation_injection"
        return decision
