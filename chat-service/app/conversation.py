"""Application configuration for Promption conversation history."""
import os
from promption.conversation import (
    ConversationStore as BaseConversationStore,
    MemoryConversationBackend,
    SQLiteConversationBackend,
    RedisConversationBackend,
)
from .config import settings


def create_conversation_backend():
    env_workers = os.getenv("CHAT_SERVICE_WORKERS") or os.getenv("PROMPTION_WORKERS")
    workers = int(env_workers) if env_workers is not None else int(getattr(settings, "workers", 1))
    env_backend = os.getenv("PROMPTION_STORAGE_BACKEND")
    backend_mode = (env_backend if env_backend is not None else getattr(settings, "storage_backend", "memory")).lower()

    if workers > 1 and backend_mode == "memory":
        raise ValueError(
            "Incompatible configuration: in-memory conversation store cannot be used with multiple workers. "
            "Configure a shared backend (e.g. 'sqlite' or 'redis')."
        )

    if backend_mode == "sqlite":
        db_path = getattr(settings, "sqlite_db_path", "data/conversations.db")
        return SQLiteConversationBackend(db_path)
    elif backend_mode == "redis":
        import redis
        client = redis.from_url(getattr(settings, "redis_url", "redis://localhost:6379/0"))
        return RedisConversationBackend(client)
    else:
        return MemoryConversationBackend()


class ConversationStore(BaseConversationStore):
    def __init__(self, backend=None):
        eff_backend = backend if backend is not None else create_conversation_backend()
        super().__init__(tenant_id=settings.tenant_id, backend=eff_backend)


store = ConversationStore()
