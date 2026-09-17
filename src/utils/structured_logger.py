"""Structured logging system for multi-user deployments."""
from __future__ import annotations

import json
import hashlib
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.config import load_config

_config = load_config()
MAX_LOG_ENTRIES = max(1000, int(os.environ.get("PROMPTION_MAX_LOG_ENTRIES", "10000")))


@dataclass
class LogEntry:
    timestamp: str
    level: str
    category: str
    tenant_id: str | None
    user_id: str | None
    roles: list[str] | None
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class StructuredLogger:
    """Thread-safe structured logger with in-memory storage for multi-user access."""

    def __init__(self, max_entries: int = MAX_LOG_ENTRIES):
        self._logs: deque[LogEntry] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._file_path = Path(_config["logging"].get("file", "logs/system.log"))
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_from_file()

    def _load_from_file(self) -> None:
        """Restore structured JSONL entries after a process restart."""
        if not self._file_path.exists():
            return
        try:
            lines = self._file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line in lines[-self._logs.maxlen:]:
            try:
                payload = json.loads(line)
                self._logs.append(LogEntry(**payload))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

    def log(
        self,
        level: str,
        category: str,
        message: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        roles: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a structured log entry."""
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level.upper(),
            category=category,
            tenant_id=tenant_id,
            user_id=user_id,
            roles=roles,
            message=message,
            details=details,
        )

        with self._lock:
            self._logs.append(entry)
            self._write_to_file(entry)

        # Also log to standard logger for backward compatibility
        logger = logging.getLogger("pif")
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(log_level, f"[{category}] {message}")

    def _write_to_file(self, entry: LogEntry) -> None:
        """Write log entry to file (JSONL format)."""
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass  # Don't fail if file write fails

    def get_logs(
        self,
        limit: int = 100,
        level: str | None = None,
        category: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        since: str | None = None,
    ) -> list[dict]:
        """Retrieve filtered logs."""
        with self._lock:
            logs = list(self._logs)

        # Apply filters
        if level:
            logs = [log for log in logs if log.level == level.upper()]
        if category:
            logs = [log for log in logs if log.category == category]
        if tenant_id:
            logs = [log for log in logs if log.tenant_id == tenant_id]
        if user_id:
            logs = [log for log in logs if log.user_id == user_id]
        if since:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            logs = [log for log in logs if datetime.fromisoformat(log.timestamp) >= since_dt]

        # Return most recent first, limited
        safe_limit = max(0, min(int(limit), self._logs.maxlen))
        if safe_limit == 0:
            return []
        return [log.to_dict() for log in reversed(logs[-safe_limit:])]

    def get_categories(self) -> list[str]:
        """Get all unique log categories."""
        with self._lock:
            return sorted({log.category for log in self._logs})

    def get_tenants(self) -> list[str]:
        """Get all unique tenant IDs."""
        with self._lock:
            return sorted({log.tenant_id for log in self._logs if log.tenant_id})

    def clear(self) -> None:
        """Clear all logs (admin only)."""
        with self._lock:
            self._logs.clear()


# Global instance
_structured_logger = StructuredLogger()


def log_filter_decision(
    decision: str,
    confidence: float,
    tenant_id: str,
    user_id: str | None = None,
    roles: list[str] | None = None,
    text: str = "",
    layers: dict | None = None,
) -> None:
    """Log a filter decision with structured data."""
    _structured_logger.log(
        level="INFO",
        category="filter",
        message=f"Filter decision: {decision} (confidence: {confidence:.2f})",
        tenant_id=tenant_id,
        user_id=user_id,
        roles=roles,
        details={
            "decision": decision,
            "confidence": confidence,
            "text_fingerprint": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16] if text else None,
            "text_length": len(text or ""),
            "layers": layers,
        },
    )


def log_authorization(
    allowed: bool,
    endpoint: str,
    roles: list[str],
    tenant_id: str,
    user_id: str | None = None,
    reason: str | None = None,
) -> None:
    """Log an authorization decision."""
    _structured_logger.log(
        level="INFO" if allowed else "WARNING",
        category="authorization",
        message=f"Auth {'allowed' if allowed else 'blocked'}: {endpoint}",
        tenant_id=tenant_id,
        user_id=user_id,
        roles=roles,
        details={
            "allowed": allowed,
            "endpoint": endpoint,
            "reason": reason,
        },
    )


def log_output_guard(
    action: str,
    categories: list[str],
    tenant_id: str,
    user_id: str | None = None,
    matches: int = 0,
    risk: float = 0.0,
) -> None:
    """Log an output guard decision."""
    _structured_logger.log(
        level="INFO" if action == "PASS" else "WARNING",
        category="output_guard",
        message=f"OutputGuard action: {action} (matches: {matches})",
        tenant_id=tenant_id,
        user_id=user_id,
        details={
            "action": action,
            "categories": categories,
            "matches": matches,
            "risk": risk,
        },
    )


def log_external_event(
    *,
    level: str,
    category: str,
    message: str,
    tenant_id: str,
    user_id: str | None = None,
    roles: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Store a sanitized event emitted by another trusted backend service."""
    _structured_logger.log(
        level=level,
        category=category,
        message=message,
        tenant_id=tenant_id,
        user_id=user_id,
        roles=roles,
        details=details or {},
    )


def get_structured_logger() -> StructuredLogger:
    """Get the global structured logger instance."""
    return _structured_logger
