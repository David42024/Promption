"""Runtime security controls shared by chat requests and the admin panel."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import filelock

logger = logging.getLogger(__name__)

_DEFAULT = {
    "filter_enabled": True,
    "output_guard_enabled": True,
    "updated_at": None,
    "updated_by": None,
    "history": [],
    "version": 1,
}


class StatePersistenceError(Exception):
    """Raised when security state cannot be saved or updated atomically."""


class SecurityStateBackend:
    """Base interface for security state backends."""

    def get_state(self) -> dict:
        raise NotImplementedError

    def update_state(
        self, action: str, enabled: bool | None, updated_by: str, expected_version: int | None = None
    ) -> dict:
        raise NotImplementedError


def _is_pid_alive(pid: int) -> bool:
    """Check if process with given PID is alive.

    If process existence cannot be determined (e.g. psutil missing or platform limitation),
    conservatively assumes the process is alive to prevent removing active locks.
    """
    if pid <= 0:
        return False
    try:
        import psutil
        return bool(psutil.pid_exists(pid))
    except (ImportError, ModuleNotFoundError):
        return True


class _ProcessFileLock:
    """Cross-process file lock backed by OS-level advisory locking (filelock) for Windows and POSIX."""

    def __init__(self, lock_path: Path, timeout: float = 10.0, stale_seconds: float = 5.0):
        self.lock_path = Path(lock_path)
        self.timeout = timeout
        self.stale_seconds = stale_seconds
        self._fd: int | None = None
        self._os_lock = filelock.FileLock(str(self.lock_path.with_suffix(".oslock")), timeout=self.timeout)

    def _recover_stale_lock(self) -> None:
        try:
            if not self.lock_path.exists():
                return
            st = self.lock_path.stat()
            age = time.time() - st.st_mtime
            if age <= self.stale_seconds:
                return

            # Mutex for recovery to eliminate races between multiple recovering workers
            rec_lock = self.lock_path.with_suffix(".recover")
            rec_fd = None
            try:
                rec_fd = os.open(str(rec_lock), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                try:
                    os.write(rec_fd, f"{os.getpid()}:{time.time()}".encode("utf-8"))
                except OSError:
                    pass
            except OSError:
                try:
                    if rec_lock.exists():
                        rec_content = rec_lock.read_text(encoding="utf-8").strip()
                        rec_stale = False
                        if ":" in rec_content:
                            try:
                                rec_pid = int(rec_content.split(":")[0])
                                if not _is_pid_alive(rec_pid):
                                    rec_stale = True
                            except (ValueError, TypeError):
                                rec_stale = True
                        else:
                            rec_stale = True

                        # Never delete the recovery mutex solely by age while its owner process is alive
                        if rec_stale and (time.time() - rec_lock.stat().st_mtime) > self.stale_seconds:
                            # Protect against concurrent deleters using OS-level lock (Windows/POSIX)
                            meta_oslock = filelock.FileLock(str(self.lock_path.with_suffix(".recover.oslock")), timeout=0)
                            try:
                                meta_oslock.acquire(timeout=0)
                            except filelock.Timeout:
                                return

                            try:
                                # Re-verify that rec_lock has not been replaced by another owner
                                current_rec = rec_lock.read_text(encoding="utf-8").strip()
                                if current_rec == rec_content:
                                    if ":" in current_rec:
                                        try:
                                            curr_rpid = int(current_rec.split(":")[0])
                                            if _is_pid_alive(curr_rpid):
                                                return
                                        except (ValueError, TypeError):
                                            pass
                                    rec_lock.unlink()
                            finally:
                                try:
                                    meta_oslock.release()
                                except Exception:
                                    pass
                except OSError:
                    pass
                return

            try:
                if not self.lock_path.exists():
                    return
                content = self.lock_path.read_text(encoding="utf-8").strip()
                is_stale = False
                if ":" in content:
                    try:
                        pid = int(content.split(":")[0])
                        if not _is_pid_alive(pid):
                            is_stale = True
                    except (ValueError, TypeError):
                        is_stale = True
                else:
                    is_stale = True

                if is_stale:
                    try:
                        # Ensure lock has not been replaced by an active owner
                        current_content = self.lock_path.read_text(encoding="utf-8").strip()
                        if current_content == content:
                            if ":" in current_content:
                                try:
                                    curr_pid = int(current_content.split(":")[0])
                                    if _is_pid_alive(curr_pid):
                                        return
                                except (ValueError, TypeError):
                                    pass
                            self.lock_path.unlink()
                            logger.warning("Recovered abandoned stale process lock at %s (age=%.2fs)", self.lock_path, age)
                    except OSError:
                        pass
            finally:
                if rec_fd is not None:
                    try:
                        os.close(rec_fd)
                    except OSError:
                        pass
                    try:
                        rec_lock.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

    def __enter__(self):
        start = time.time()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._os_lock.acquire(timeout=self.timeout)
        except filelock.Timeout as exc:
            raise StatePersistenceError(f"Timed out acquiring process lock on {self.lock_path}") from exc

        try:
            self._recover_stale_lock()
            while True:
                try:
                    self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    try:
                        os.write(self._fd, f"{os.getpid()}:{time.time()}".encode("utf-8"))
                    except OSError:
                        pass
                    return self
                except OSError:
                    self._recover_stale_lock()
                    if time.time() - start > self.timeout:
                        raise StatePersistenceError(f"Timed out acquiring process lock on {self.lock_path}")
                    time.sleep(0.01)
        except Exception:
            try:
                self._os_lock.release()
            except Exception:
                pass
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                try:
                    if self.lock_path.exists():
                        self.lock_path.unlink()
                except OSError:
                    pass
        finally:
            try:
                self._os_lock.release()
            except Exception:
                pass


_path_locks: dict[str, threading.RLock] = {}
_path_locks_guard = threading.Lock()


def _get_path_lock(path: Path) -> threading.RLock:
    try:
        resolved = str(path.resolve())
    except Exception:
        resolved = str(path)
    with _path_locks_guard:
        if resolved not in _path_locks:
            _path_locks[resolved] = threading.RLock()
        return _path_locks[resolved]


class FileSecurityBackend(SecurityStateBackend):
    """Local JSON file backend with atomic write via temp file, cross-process lock and atomic replace."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.lock_path = self.path.parent / f".{self.path.name}.lock"
        self._lock = _get_path_lock(self.path)
        self._memory = dict(_DEFAULT)

    def read_state(self) -> dict:
        try:
            if self.path.exists():
                content = self.path.read_text(encoding="utf-8")
                data = json.loads(content)
                merged = {**_DEFAULT, **data}
                if not isinstance(merged.get("version"), int):
                    merged["version"] = 1
                return merged
            # Missing file always returns safe defaults, never stale in-memory modifications
            return dict(_DEFAULT)
        except (OSError, ValueError, TypeError) as exc:
            logger.error("Failed to read security state file at %s: %s. Using safe defaults.", self.path, exc)
            return dict(_DEFAULT)

    def write_state(self, state: dict) -> None:
        temp_path = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Unique temp file in the same directory ensures atomic os.replace across platforms
            temp_path = self.path.parent / f".tmp_{self.path.name}_{uuid.uuid4().hex}"
            temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp_path, self.path)
            # Memory updated ONLY after persistence succeeds!
            self._memory = dict(state)
        except OSError as exc:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            logger.error("Atomic write failed for security state at %s: %s", self.path, exc)
            raise StatePersistenceError(f"Failed to atomically persist security state to {self.path}: {exc}") from exc

    def get_state(self) -> dict:
        with self._lock:
            return self.read_state()

    def update_state(
        self, action: str, enabled: bool | None, updated_by: str, expected_version: int | None = None
    ) -> dict:
        with self._lock, _ProcessFileLock(self.lock_path):
            current = self.read_state()
            cur_version = int(current.get("version", 1))
            if expected_version is not None and expected_version != cur_version:
                raise StatePersistenceError(
                    f"Version conflict: expected version {expected_version}, but current version is {cur_version}."
                )

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
            current["version"] = cur_version + 1
            current["history"] = [
                {"action": label, "at": now, "by": updated_by},
                *(current.get("history") or []),
            ][:20]
            self.write_state(current)
            return current


class SQLiteSecurityBackend(SecurityStateBackend):
    """Shared SQLite security controls backend with transactional versioning for multi-process deployments."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS security_controls (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data_json TEXT NOT NULL,
                    version INTEGER DEFAULT 1
                )
            """)

    def get_state(self) -> dict:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT data_json, version FROM security_controls WHERE id = 1")
            row = cur.fetchone()
            if not row:
                return dict(_DEFAULT)
            try:
                data = json.loads(row[0])
                merged = {**_DEFAULT, **data}
                merged["version"] = row[1]
                return merged
            except Exception:
                return dict(_DEFAULT)

    def update_state(
        self, action: str, enabled: bool | None, updated_by: str, expected_version: int | None = None
    ) -> dict:
        with self._lock, self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("SELECT data_json, version FROM security_controls WHERE id = 1")
            row = cur.fetchone()
            if row:
                current = {**_DEFAULT, **json.loads(row[0])}
                cur_version = row[1]
            else:
                current = dict(_DEFAULT)
                cur_version = 1

            if expected_version is not None and expected_version != cur_version:
                conn.rollback()
                raise StatePersistenceError(
                    f"Version conflict: expected version {expected_version}, but current version is {cur_version}."
                )

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
                conn.rollback()
                raise ValueError(f"Unknown security action: {action}")

            now = datetime.now(timezone.utc).isoformat()
            current["updated_at"] = now
            current["updated_by"] = updated_by
            current["version"] = cur_version + 1
            current["history"] = [
                {"action": label, "at": now, "by": updated_by},
                *(current.get("history") or []),
            ][:20]

            conn.execute(
                "INSERT INTO security_controls (id, data_json, version) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, version=excluded.version",
                (json.dumps(current), current["version"]),
            )
            conn.commit()
            return current


class RedisSecurityBackend(SecurityStateBackend):
    """Distributed security state backend using Redis with atomic versioned updates."""

    def __init__(self, redis_client: Any, key: str = "promption:security_state"):
        self.redis = redis_client
        self.key = key

    def get_state(self) -> dict:
        try:
            raw = self.redis.get(self.key)
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                data = json.loads(raw)
                merged = {**_DEFAULT, **data}
                if not isinstance(merged.get("version"), int):
                    merged["version"] = 1
                return merged
        except Exception as exc:
            logger.error("Failed to read security state from Redis key %s: %s. Using safe defaults.", self.key, exc)
            return dict(_DEFAULT)
        return dict(_DEFAULT)

    def update_state(
        self, action: str, enabled: bool | None, updated_by: str, expected_version: int | None = None
    ) -> dict:
        max_attempts = 10
        for _ in range(max_attempts):
            pipe = self.redis.pipeline()
            try:
                pipe.watch(self.key)
                raw = pipe.get(self.key)
                if raw is not None:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    current = {**_DEFAULT, **json.loads(raw)}
                else:
                    current = dict(_DEFAULT)

                cur_version = int(current.get("version", 1))
                if expected_version is not None and expected_version != cur_version:
                    pipe.unwatch()
                    raise StatePersistenceError(
                        f"Version conflict: expected version {expected_version}, but current version is {cur_version}."
                    )

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
                    pipe.unwatch()
                    raise ValueError(f"Unknown security action: {action}")

                now = datetime.now(timezone.utc).isoformat()
                current["updated_at"] = now
                current["updated_by"] = updated_by
                current["version"] = cur_version + 1
                current["history"] = [
                    {"action": label, "at": now, "by": updated_by},
                    *(current.get("history") or []),
                ][:20]

                pipe.multi()
                pipe.set(self.key, json.dumps(current, ensure_ascii=False))
                pipe.execute()
                return current
            except StatePersistenceError:
                raise
            except Exception:
                continue
            finally:
                try:
                    pipe.reset()
                except Exception:
                    pass

        raise StatePersistenceError("Failed to update security state in Redis after maximum concurrency retry attempts.")


class SecurityStateStore:
    """Store for runtime security controls with atomic persistence and versioning."""

    def __init__(self, path: str, backend: SecurityStateBackend | None = None):
        self.path = Path(path)
        self.backend = backend or FileSecurityBackend(self.path)

    def get(self) -> dict:
        state = self.backend.get_state()
        return {
            "filter_enabled": bool(state.get("filter_enabled", True)),
            "output_guard_enabled": bool(state.get("output_guard_enabled", True)),
            "updated_at": state.get("updated_at"),
            "updated_by": state.get("updated_by"),
            "history": list(state.get("history") or [])[:20],
            "version": int(state.get("version", 1)),
        }

    def update(
        self, action: str, enabled: bool | None, updated_by: str, expected_version: int | None = None
    ) -> dict:
        self.backend.update_state(action, enabled, updated_by, expected_version=expected_version)
        return self.get()
