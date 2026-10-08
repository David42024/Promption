import sys
from pathlib import Path

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

import pytest
from promption.api.models import FilterResponse
from app.routes import (
    _review_conversation,
    _request_review_cache,
    _request_eval_counts,
    ConversationBlocked,
)
from app.models import ChatRequest, User, UserRole


class DummyFilterClient:
    def __init__(self, blocked=False):
        self.blocked = blocked
        self.call_count = 0

    async def filter_prompt(self, text, identity, use_ml=True, messages=None, timeout=None):
        self.call_count += 1
        msg_count = len(messages) if messages else 0
        if self.blocked:
            return FilterResponse(
                text=text,
                decision="BLOCKED",
                blocked=True,
                confidence=0.9,
                latency_ms=1.0,
                reason="injection",
                layers={"conversation": {"message_count": msg_count, "blocked": True}},
                sanitized="",
                classification="MALICIOUS",
                requires_review=True,
                requires_output_guard=False,
            )
        return FilterResponse(
            text=text,
            decision="ALLOWED",
            blocked=False,
            confidence=0.9,
            latency_ms=1.0,
            reason="benign",
            layers={"conversation": {"message_count": msg_count, "blocked": False}},
            sanitized=text,
            classification="BENIGN",
            requires_review=False,
            requires_output_guard=False,
        )


@pytest.mark.asyncio
async def test_review_conversation_deduplicates_identical_call_in_same_request():
    _request_review_cache.set({})
    _request_eval_counts.set({"conversation": 0, "deduplicated": 0})

    client = DummyFilterClient(blocked=False)
    user = User(id="user1", name="User One", email="u1@test.com", roles=[UserRole.CUSTOMER], authenticated=True)
    req = ChatRequest(text="hola", user=user)
    messages = [{"role": "user", "content": "hola"}]

    # First call
    await _review_conversation(messages, req, client, enabled=True)
    assert client.call_count == 1
    counts = _request_eval_counts.get()
    assert counts["conversation"] == 1
    assert counts["deduplicated"] == 0

    # Second call with identical content & request
    await _review_conversation(messages, req, client, enabled=True)
    assert client.call_count == 1  # Not called again
    assert counts["deduplicated"] == 1


@pytest.mark.asyncio
async def test_review_conversation_invalidates_on_changed_identity_or_role():
    _request_review_cache.set({})
    _request_eval_counts.set({"conversation": 0, "deduplicated": 0})

    client = DummyFilterClient(blocked=False)
    user1 = User(id="user1", name="User One", email="u1@test.com", roles=[UserRole.CUSTOMER], authenticated=True)
    req1 = ChatRequest(text="hola", user=user1)
    messages = [{"role": "user", "content": "hola"}]

    await _review_conversation(messages, req1, client, enabled=True)
    assert client.call_count == 1

    # Same content, different role
    user2 = User(id="user1", name="User One", email="u1@test.com", roles=[UserRole.ADMIN], authenticated=True)
    req2 = ChatRequest(text="hola", user=user2)
    await _review_conversation(messages, req2, client, enabled=True)
    assert client.call_count == 2

    # Same content, different user ID
    user3 = User(id="user2", name="User Two", email="u2@test.com", roles=[UserRole.CUSTOMER], authenticated=True)
    req3 = ChatRequest(text="hola", user=user3)
    await _review_conversation(messages, req3, client, enabled=True)
    assert client.call_count == 3


@pytest.mark.asyncio
async def test_review_conversation_reinspects_on_new_messages_or_tool_evidence():
    _request_review_cache.set({})
    _request_eval_counts.set({"conversation": 0, "deduplicated": 0})

    client = DummyFilterClient(blocked=False)
    user = User(id="user1", name="User One", email="u1@test.com", roles=[UserRole.CUSTOMER], authenticated=True)
    req = ChatRequest(text="hola", user=user)
    messages = [{"role": "user", "content": "hola"}]

    await _review_conversation(messages, req, client, enabled=True)
    assert client.call_count == 1

    # New tool evidence added
    new_messages = messages + [{"role": "tool", "tool_name": "make_doc", "content": '{"leak": "data"}'}]
    await _review_conversation(new_messages, req, client, enabled=True)
    assert client.call_count == 2


@pytest.mark.asyncio
async def test_review_conversation_does_not_cache_blocked_or_failed_evaluations():
    _request_review_cache.set({})
    _request_eval_counts.set({"conversation": 0, "deduplicated": 0})

    client = DummyFilterClient(blocked=True)
    user = User(id="user1", name="User One", email="u1@test.com", roles=[UserRole.CUSTOMER], authenticated=True)
    req = ChatRequest(text="attack", user=user)
    messages = [{"role": "user", "content": "attack"}]

    with pytest.raises(ConversationBlocked):
        await _review_conversation(messages, req, client, enabled=True)

    cache = _request_review_cache.get()
    assert len(cache) == 0  # Not cached as safe
