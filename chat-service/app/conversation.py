"""Application configuration for Promption conversation history."""
from promption.conversation import ConversationStore as BaseConversationStore
from .config import settings


class ConversationStore(BaseConversationStore):
    def __init__(self):
        super().__init__(tenant_id=settings.tenant_id)


store = ConversationStore()
