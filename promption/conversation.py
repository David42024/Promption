"""Bounded conversation history owned by the chat service."""
from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict

from typing import Protocol

from .conversation_guard import ConversationLimitError, validate_messages


class ConversationUser(Protocol):
    id: str
    roles: list
    authenticated: bool

TTL_SECONDS = 8 * 60 * 60
MAX_CONVERSATIONS = 500
MAX_TURNS = 12
MAX_CONTEXT_CHARS = 12_000


class ConversationStore:
    def __init__(self, *, tenant_id: str | None = None, ttl_seconds: int = TTL_SECONDS,
                 max_conversations: int = MAX_CONVERSATIONS, max_turns: int = MAX_TURNS,
                 max_context_chars: int = MAX_CONTEXT_CHARS):
        if min(ttl_seconds, max_conversations, max_turns, max_context_chars) < 1:
            raise ValueError("Conversation limits must be positive")
        self.tenant_id = tenant_id
        self.ttl_seconds = ttl_seconds
        self.max_conversations = max_conversations
        self.max_turns = max_turns
        self.max_context_chars = max_context_chars
        self._items = OrderedDict()
        self._lock = threading.Lock()

    def _key(self, conversation_id: str | None, user: ConversationUser):
        try:
            identifier = str(uuid.UUID(conversation_id or ""))
        except (ValueError, AttributeError, TypeError):
            return None
        roles = tuple(sorted(role.value if hasattr(role, "value") else str(role)
                             for role in user.roles))
        return self.tenant_id, user.id, roles, bool(user.authenticated), identifier

    def _prune(self, now: float):
        for key in list(self._items):
            if now - self._items[key]["updated"] > self.ttl_seconds:
                del self._items[key]
        while len(self._items) > self.max_conversations:
            self._items.popitem(last=False)

    def snapshot(self, conversation_id: str | None, user: ConversationUser) -> tuple[list[dict], bool]:
        key = self._key(conversation_id, user)
        if key is None:
            return [], False
        with self._lock:
            self._prune(time.monotonic())
            item = self._items.get(key)
            if not item:
                return [], False
            self._items.move_to_end(key)
            pairs = list(item["pairs"])
        selected = []
        total = 0
        for pair in reversed(pairs):
            size = len(pair["user"]) + len(pair["assistant"])
            if total + size > self.max_context_chars:
                break
            selected.append(pair)
            total += size
        selected.reverse()
        messages = []
        for pair in selected:
            messages.extend((
                {"role": "user", "content": pair["user"]},
                {"role": "assistant", "content": pair["assistant"]},
            ))
        protected = any(pair["tier"] in {"interno", "confidencial", "restringido"}
                        for pair in selected)
        return messages, protected

    def security_snapshot(self, conversation_id: str | None, user: ConversationUser) -> list[dict]:
        key = self._key(conversation_id, user)
        if key is None:
            return []
        with self._lock:
            self._prune(time.monotonic())
            item = self._items.get(key)
            if not item:
                return []
            if item.get("security_overflow"):
                raise ConversationLimitError("Security evidence exceeds limits; start a new conversation")
            return [dict(message) for message in item.get("security", [])]

    def append_security(self, conversation_id: str | None, user: ConversationUser, messages: list[dict]) -> None:
        key = self._key(conversation_id, user)
        if key is None:
            return
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            item = self._items.setdefault(key, {"pairs": [], "updated": now})
            evidence = item.get("security", []) + messages
            try:
                validate_messages(evidence)
            except ConversationLimitError:
                item["security_overflow"] = True
                raise
            item["security"] = [dict(message) for message in evidence]
            item["updated"] = now
            self._items.move_to_end(key)
            self._prune(now)

    def display(self, conversation_id: str | None, user: ConversationUser) -> list[dict]:
        key = self._key(conversation_id, user)
        if key is None:
            return []
        with self._lock:
            self._prune(time.monotonic())
            item = self._items.get(key)
            if not item:
                return []
            pairs = list(item["pairs"])
        visible = []
        for pair in pairs:
            visible.append({"from": "user", "text": pair["user"]})
            visible.append({"from": "bot", "text": pair["assistant"],
                            "actions": pair["actions"]})
        return visible

    def record(self, conversation_id: str | None, user: ConversationUser, prompt: str,
               response: str, tier: str, actions: list[dict], *, security_recorded: bool = False):
        key = self._key(conversation_id, user)
        if key is None:
            return
        if not security_recorded:
            self.append_security(conversation_id, user, [{"role": "user", "content": prompt}])
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            item = self._items.setdefault(key, {"pairs": [], "updated": now})
            item["pairs"].append({"user": prompt[:5000], "assistant": response[:8000],
                                  "tier": tier, "actions": actions})
            item["pairs"] = item["pairs"][-self.max_turns:]
            item["updated"] = now
            self._items.move_to_end(key)
            self._prune(now)
