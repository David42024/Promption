"""Conversation context and authorization boundaries."""
import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

from app import routes
from app.conversation import ConversationStore
from app.models import ChatRequest, ConversationHistoryRequest, User


class Filter:
    async def filter_prompt(self, **kwargs):
        blocked = kwargs["text"] == "ataque bloqueado"
        return SimpleNamespace(blocked=blocked, classification="MALICIOUS" if blocked else "BENIGN",
                               layers={}, reason="test" if blocked else "", confidence=0.9)

    async def output_guard(self, **kwargs):
        return {"action": "PASS"}

    async def audit_event(self, **kwargs):
        return None


class LLM:
    def __init__(self):
        self.calls = []

    async def generate_tool_turn(self, messages, tools, model_id=None):
        self.calls.append((list(messages), [tool["function"]["name"] for tool in tools]))
        return {"model_id": "test", "model": "test", "provider": "openai",
                "text": f"Respuesta {len(self.calls)}", "calls": []}


def user(role="customer", user_id="u1"):
    return User(id=user_id, name="Persona", email="u@example.com",
                roles=[role], authenticated=True)


def request(text, person, conversation_id):
    return ChatRequest(text=text, user=person, context={"conversation_id": conversation_id})


def test_next_turn_receives_previous_turns_and_history_endpoint(monkeypatch):
    store = ConversationStore()
    llm = LLM()
    monkeypatch.setattr(routes, "store", store)
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)
    identifier = str(uuid.uuid4())
    person = user()

    first = asyncio.run(routes.chat(request("Recuerda azulejo", person, identifier)))
    second = asyncio.run(routes.chat(request("¿Qué palabra te dije?", person, identifier)))

    assert not first.blocked and not second.blocked
    second_messages = llm.calls[1][0]
    assert second_messages[-3:] == [
        {"role": "user", "content": "Recuerda azulejo"},
        {"role": "assistant", "content": "Respuesta 1"},
        {"role": "user", "content": "¿Qué palabra te dije?"},
    ]
    history = asyncio.run(routes.conversation_history(
        ConversationHistoryRequest(conversation_id=identifier, user=person)))
    assert [item["from"] for item in history["messages"]] == ["user", "bot", "user", "bot"]
    assert len(store.display(identifier, user(user_id="another"))) == 0
    assert len(store.display(identifier, user(role="ventas"))) == 0

    asyncio.run(routes.chat(request("Otra conversación", person, str(uuid.uuid4()))))
    assert llm.calls[2][0][-1] == {"role": "user", "content": "Otra conversación"}
    assert not any(message["content"] == "Recuerda azulejo" for message in llm.calls[2][0])


def test_blocked_input_is_not_saved_and_protected_history_removes_web(monkeypatch):
    store = ConversationStore()
    llm = LLM()
    monkeypatch.setattr(routes, "store", store)
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: llm)
    identifier = str(uuid.uuid4())
    person = user(role="admin")
    blocked = asyncio.run(routes.chat(request("ataque bloqueado", person, identifier)))
    assert blocked.blocked
    assert store.display(identifier, person) == []

    store.record(identifier, person, "Dato interno", "Respuesta interna", "confidencial", [])
    response = asyncio.run(routes.chat(request("Hola", person, identifier)))
    assert not response.blocked
    assert "web_search" not in llm.calls[0][1]
    assert "web_open" not in llm.calls[0][1]
    assert llm.calls[0][0][-3]["content"] == "Dato interno"


def test_store_bounds_and_rejects_invalid_ids():
    store = ConversationStore()
    person = user()
    identifier = str(uuid.uuid4())
    store.record("bad-id", person, "x", "y", "publico", [])
    assert store.display("bad-id", person) == []
    for number in range(15):
        store.record(identifier, person, f"pregunta {number}", "respuesta", "publico", [])
    assert len(store.display(identifier, person)) == 24
    assert store.snapshot(identifier, person)[0][0]["content"] == "pregunta 3"
