"""Application configuration for Promption runtime security controls."""
from promption.state import SecurityStateStore
from .config import settings

_store = SecurityStateStore(settings.security_state_path)


def get_security_state() -> dict:
    return _store.get()


def update_security_state(action: str, enabled: bool | None, updated_by: str) -> dict:
    return _store.update(action, enabled, updated_by)
