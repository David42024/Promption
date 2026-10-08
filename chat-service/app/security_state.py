"""Application configuration for Promption runtime security controls."""
import os
from promption.state import SecurityStateStore, FileSecurityBackend, RedisSecurityBackend
from .config import settings


def _create_security_store() -> SecurityStateStore:
    env_workers = os.getenv("CHAT_SERVICE_WORKERS") or os.getenv("PROMPTION_WORKERS")
    workers = int(env_workers) if env_workers is not None else int(getattr(settings, "workers", 1))
    env_backend = os.getenv("PROMPTION_STORAGE_BACKEND")
    backend_mode = (env_backend if env_backend is not None else getattr(settings, "storage_backend", "file")).lower()

    if workers > 1 and backend_mode in ("memory", "file"):
        raise ValueError(
            "Incompatible configuration: JSON/file security controls cannot be used with multiple workers. "
            "Configure a shared transactional backend (e.g. 'sqlite' or 'redis')."
        )

    if backend_mode == "redis":
        import redis
        client = redis.from_url(getattr(settings, "redis_url", "redis://localhost:6379/0"))
        return SecurityStateStore(settings.security_state_path, backend=RedisSecurityBackend(client))
    if backend_mode == "sqlite":
        from promption.state import SQLiteSecurityBackend
        db_path = getattr(settings, "sqlite_db_path", "data/conversations.db")
        return SecurityStateStore(settings.security_state_path, backend=SQLiteSecurityBackend(db_path))
    return SecurityStateStore(settings.security_state_path, backend=FileSecurityBackend(settings.security_state_path))


_store = _create_security_store()


def get_security_state() -> dict:
    return _store.get()


def update_security_state(action: str, enabled: bool | None, updated_by: str) -> dict:
    return _store.update(action, enabled, updated_by)
