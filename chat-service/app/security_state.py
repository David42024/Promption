"""Runtime security controls shared by chat requests and the admin panel."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import settings


_DEFAULT = {
    "filter_enabled": True,
    "output_guard_enabled": True,
    "updated_at": None,
    "updated_by": None,
    "history": [],
}


class SecurityStateStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._memory = dict(_DEFAULT)

    def _read(self) -> dict:
        try:
            if self.path.exists():
                return {**_DEFAULT, **json.loads(self.path.read_text(encoding="utf-8"))}
        except (OSError, ValueError, TypeError):
            pass
        return dict(self._memory)

    def _write(self, state: dict) -> None:
        self._memory = dict(state)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def get(self) -> dict:
        with self._lock:
            state = self._read()
        return {
            "filter_enabled": bool(state.get("filter_enabled", True)),
            "output_guard_enabled": bool(state.get("output_guard_enabled", True)),
            "updated_at": state.get("updated_at"),
            "updated_by": state.get("updated_by"),
            "history": list(state.get("history") or [])[:20],
        }

    def update(self, action: str, enabled: bool | None, updated_by: str) -> dict:
        with self._lock:
            current = self._read()
            if action == "reset":
                current = dict(_DEFAULT)
                label = "security:RESET"
            elif action == "output_guard":
                current["output_guard_enabled"] = bool(enabled)
                label = f"output-guard:{'ON' if enabled else 'OFF'}"
            elif action == "filter":
                current["filter_enabled"] = bool(enabled)
                label = f"filter:{'ON' if enabled else 'OFF'}"
            else:
                raise ValueError(f"Unknown security action: {action}")
            now = datetime.now(timezone.utc).isoformat()
            current["updated_at"] = now
            current["updated_by"] = updated_by
            current["history"] = [
                {"action": label, "at": now, "by": updated_by},
                *(current.get("history") or []),
            ][:20]
            self._write(current)
        return self.get()


_store = SecurityStateStore(settings.security_state_path)


def get_security_state() -> dict:
    return _store.get()


def update_security_state(action: str, enabled: bool | None, updated_by: str) -> dict:
    return _store.update(action, enabled, updated_by)
