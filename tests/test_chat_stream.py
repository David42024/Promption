"""Streaming progress and file delivery contracts."""
import asyncio
import base64
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
import pytest

pytestmark = pytest.mark.usefixtures("scope_in_scope")

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

from app import routes
from app.conversation import ConversationStore
from app.models import ChatRequest, User


class Filter:
    async def filter_prompt(self, **kwargs):
        return SimpleNamespace(blocked=False, classification="BENIGN", layers={"conversation": {"message_count": len(kwargs.get("messages") or []), "blocked": False}},
                               reason="", confidence=0.1)

    async def output_guard(self, **kwargs):
        return {"action": "PASS"}

    async def audit_event(self, **kwargs):
        return None


def request():
    return ChatRequest(text="Genera un archivo TXT con un resumen público.",
        user=User(id="c1", name="Cliente", email="cliente@example.com",
                  roles=["customer"], authenticated=True),
        context={"conversation_id": str(uuid.uuid4())})


def test_stream_emits_progress_and_file_attachment(monkeypatch):
    class LLM:
        calls = 0

        async def generate_tool_turn(self, messages, tools, model_id=None, force_tool=None):
            self.calls += 1
            if self.calls == 1:
                return {"model_id": "test", "model": "test", "provider": "openai",
                        "text": "Preparé el archivo.", "calls": []}
            if self.calls == 2:
                assert force_tool == "make_document"
                assert [spec["function"]["name"] for spec in tools] == ["make_document"]
                return {"model_id": "test", "model": "test", "provider": "openai", "text": "",
                        "calls": [{"id": "file1", "name": "make_document", "arguments":
                                   '{"title":"resumen","content":"Resumen público","format":"txt"}'}]}
            return {"model_id": "test", "model": "test", "provider": "openai",
                    "text": "Adjunté el archivo.", "calls": []}

    monkeypatch.setattr(routes, "store", ConversationStore())
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: LLM())

    async def collect():
        response = await routes.chat_stream(request())
        return [json.loads(frame[6:]) async for frame in response.body_iterator
                if frame.startswith("data: ")]

    events = asyncio.run(collect())
    stages = [item["stage"] for item in events if item["type"] == "status"]
    result = events[-1]["data"]
    assert "Generando archivo…" in stages
    assert "Verificando respuesta…" in stages
    assert result["blocked"] is False
    assert result["actions"][0]["type"] == "attachment"
    assert base64.b64decode(result["actions"][0]["data"]) == b"Resumen p\xc3\xbablico"


def test_file_claim_without_action_is_replaced(monkeypatch):
    class LLM:
        async def generate_tool_turn(self, messages, tools, model_id=None, force_tool=None):
            if force_tool:
                raise RuntimeError("provider unavailable")
            return {"model_id": "test", "model": "test", "provider": "openai",
                    "text": "Ya preparé el archivo para descargar.", "calls": []}

    monkeypatch.setattr(routes, "store", ConversationStore())
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: LLM())
    response = asyncio.run(routes.chat(request()))
    assert response.actions == []
    assert response.reply == "No pude adjuntar un archivo en esta respuesta. Inténtalo nuevamente."


def test_openai_forced_document_tool_choice(monkeypatch):
    from app import llm_client

    seen = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {
                    "name": "make_document", "arguments": "{}"}}]}}]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            seen.update(kwargs)
            return Response()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", Client)
    client = llm_client.LLMClient()
    client.models = [{"id": "openai", "label": "OpenAI", "provider": "openai",
                      "api": "openai_compatible", "model": "gpt-5-nano", "api_key": "test",
                      "base_url": "https://api.openai.com/v1/chat/completions",
                      "temperature": 0.2, "max_tokens": 600}]
    tools = [{"type": "function", "function": {"name": "make_document",
              "description": "archivo", "parameters": {"type": "object", "properties": {}}}}]
    asyncio.run(client.generate_tool_turn([{"role": "user", "content": "archivo"}],
                                          tools, force_tool="make_document"))
    assert seen["json"]["tool_choice"] == {
        "type": "function", "function": {"name": "make_document"}}


def test_stream_blocks_second_turn_and_can_cancel(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.models import ConversationHistoryRequest

    started = asyncio.Event()

    class SlowLLM:
        async def generate_tool_turn(self, messages, tools, model_id=None, force_tool=None):
            started.set()
            await asyncio.sleep(60)

    monkeypatch.setattr(routes, "store", ConversationStore())
    monkeypatch.setattr(routes, "get_filter_client", lambda: Filter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: SlowLLM())
    routes._active_runs.clear()
    chat_request = request()

    async def check():
        response = await routes.chat_stream(chat_request)
        await asyncio.wait_for(started.wait(), timeout=2)
        with pytest.raises(HTTPException) as error:
            await routes.chat_stream(chat_request)
        assert error.value.status_code == 409
        with pytest.raises(HTTPException) as direct_error:
            await routes.chat(chat_request)
        assert direct_error.value.status_code == 409
        cancel = await routes.cancel_chat(ConversationHistoryRequest(
            conversation_id=chat_request.context["conversation_id"],
            user=chat_request.user))
        assert cancel["cancelled"]
        events = [json.loads(frame[6:]) async for frame in response.body_iterator
                  if frame.startswith("data: ")]
        assert events[-1]["type"] == "error"
        assert "cancelada" in events[-1]["message"]
        assert not routes._active_runs

    asyncio.run(check())
