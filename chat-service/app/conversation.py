"""Bounded conversation history owned by the chat service."""
from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict

from .config import settings
from .models import User

TTL_SECONDS = 8 * 60 * 60
MAX_CONVERSATIONS = 500
MAX_TURNS = 12
MAX_CONTEXT_CHARS = 12_000


class ConversationStore:
    def __init__(self):
        self._items = OrderedDict()
        self._lock = threading.Lock()

    def _key(self, conversation_id: str | None, user: User):
        try:
            identifier = str(uuid.UUID(conversation_id or ""))
        except (ValueError, AttributeError, TypeError):
            return None
        roles = tuple(sorted(role.value if hasattr(role, "value") else str(role)
                             for role in user.roles))
        return settings.tenant_id, user.id, roles, bool(user.authenticated), identifier

    def _prune(self, now: float):
        for key in list(self._items):
            if now - self._items[key]["updated"] > TTL_SECONDS:
                del self._items[key]
        while len(self._items) > MAX_CONVERSATIONS:
            self._items.popitem(last=False)

    def snapshot(self, conversation_id: str | None, user: User) -> tuple[list[dict], bool]:
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
            if total + size > MAX_CONTEXT_CHARS:
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

    def display(self, conversation_id: str | None, user: User) -> list[dict]:
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

    def record(self, conversation_id: str | None, user: User, prompt: str,
               response: str, tier: str, actions: list[dict]):
        key = self._key(conversation_id, user)
        if key is None:
            return
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            item = self._items.setdefault(key, {"pairs": [], "updated": now})
            item["pairs"].append({"user": prompt[:5000], "assistant": response[:8000],
                                  "tier": tier, "actions": actions})
            item["pairs"] = item["pairs"][-MAX_TURNS:]
            item["updated"] = now
            self._items.move_to_end(key)
            self._prune(now)


store = ConversationStore()
