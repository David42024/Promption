"""Regression tests for Defect 3 (Tool deduplication transcript and actions)."""
import asyncio
import json
from types import SimpleNamespace
import pytest

pytestmark = pytest.mark.usefixtures("scope_in_scope")

import sys
from pathlib import Path

CHAT_SERVICE_DIR = Path(__file__).resolve().parent.parent / "chat-service"
if str(CHAT_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE_DIR))

from app.models import ChatRequest, User, UserRole
import app.routes as routes


def test_tool_deduplication_preserves_transcript_and_prevents_duplicate_actions(monkeypatch):
    """
    Two equivalent make_document calls with different key ordering:
    - MCP tool is executed only once.
    - Both tool_call_ids have corresponding role: 'tool' messages in messages/transcript.
    - Only one attachment action is returned in actions.
    - Turn 2 receives a valid transcript containing both tool results.
    """
    executions = []
    real_executor = routes.get_mcp_executor()
    orig_execute = real_executor.execute

    async def wrapped_execute(name, args, roles, authenticated=True):
        executions.append((name, args))
        return await orig_execute(name, args, roles, authenticated=authenticated)

    monkeypatch.setattr(real_executor, "execute", wrapped_execute)

    received_turn2_messages = []

    class MockLLM:
        turn = 0

        async def generate_tool_turn(self, messages, tools, model_id=None, deadline=None):
            self.turn += 1
            if self.turn == 1:
                return {
                    "model_id": "test",
                    "model": "test",
                    "provider": "openai",
                    "text": "",
                    "calls": [
                        {
                            "id": "call_first",
                            "name": "make_document",
                            "arguments": json.dumps({"title": "reporte", "content": "Resumen autorizado", "format": "txt"}),
                        },
                        {
                            "id": "call_second",
                            "name": "make_document",
                            "arguments": json.dumps({"format": "txt", "title": "reporte", "content": "Resumen autorizado"}),
                        },
                    ],
                }
            elif self.turn == 2:
                received_turn2_messages.extend(messages)
                return {
                    "model_id": "test",
                    "model": "test",
                    "provider": "openai",
                    "text": "Documento preparado sin duplicados.",
                    "calls": [],
                }

    class MockFilter:
        async def filter_prompt(self, **kwargs):
            return SimpleNamespace(
                blocked=False,
                classification="BENIGN",
                layers={"conversation": {"message_count": len(kwargs.get("messages") or []), "blocked": False}},
                reason="",
                confidence=0.1,
            )

        async def output_guard(self, **kwargs):
            return {"action": "PASS", "text": kwargs.get("text", "")}

        async def audit_event(self, **kwargs):
            return None

    monkeypatch.setattr(routes, "get_filter_client", lambda: MockFilter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: MockLLM())

    user = User(id="admin-1", name="Admin", email="admin@example.com", roles=["admin"], authenticated=True)
    req = ChatRequest(
        text="Dame el reporte mensual de facturación",
        user=user,
    )

    resp = asyncio.run(routes.chat(req))

    # 1. Tool executed once only
    make_doc_executions = [e for e in executions if e[0] == "make_document"]
    assert len(make_doc_executions) == 1, f"Expected 1 make_document execution, got {len(make_doc_executions)}"

    # 2. Only 1 attachment action (fails before fix: duplicate action appended)
    attachments = [a for a in resp.actions if a.get("type") == "attachment"]
    assert len(attachments) == 1, f"Expected 1 attachment in actions, got {len(attachments)}"

    # 3. Turn 2 received valid transcript with both tool_call_ids answered (fails before fix: call_second skipped by continue)
    tool_messages = [m for m in received_turn2_messages if m.get("role") == "tool"]
    tool_call_ids = [m.get("tool_call_id") for m in tool_messages]
    assert "call_first" in tool_call_ids, "Missing call_first in transcript messages"
    assert "call_second" in tool_call_ids, "Missing call_second in transcript messages"
    turn_tool_messages = [m for m in tool_messages if m.get("tool_call_id") in ("call_first", "call_second")]
    assert len(turn_tool_messages) == 2, f"Expected 2 turn tool messages in transcript, got {len(turn_tool_messages)}"


def test_tool_deduplication_different_arguments_not_reused(monkeypatch):
    """Different arguments must not reuse cached results."""
    executions = []
    real_executor = routes.get_mcp_executor()
    orig_execute = real_executor.execute

    async def wrapped_execute(name, args, roles, authenticated=True):
        executions.append((name, args))
        return await orig_execute(name, args, roles, authenticated=authenticated)

    monkeypatch.setattr(real_executor, "execute", wrapped_execute)

    class MockLLM:
        turn = 0

        async def generate_tool_turn(self, messages, tools, model_id=None, deadline=None):
            self.turn += 1
            if self.turn == 1:
                return {
                    "model_id": "test",
                    "model": "test",
                    "provider": "openai",
                    "text": "",
                    "calls": [
                        {
                            "id": "call_1",
                            "name": "make_document",
                            "arguments": json.dumps({"title": "rep1", "content": "Resumen uno", "format": "txt"}),
                        },
                        {
                            "id": "call_2",
                            "name": "make_document",
                            "arguments": json.dumps({"title": "rep2", "content": "Resumen dos", "format": "txt"}),
                        },
                    ],
                }
            return {
                "model_id": "test",
                "model": "test",
                "provider": "openai",
                "text": "Listos ambos documentos.",
                "calls": [],
            }

    class MockFilter:
        async def filter_prompt(self, **kwargs):
            return SimpleNamespace(
                blocked=False,
                classification="BENIGN",
                layers={"conversation": {"message_count": len(kwargs.get("messages") or []), "blocked": False}},
                reason="",
                confidence=0.1,
            )

        async def output_guard(self, **kwargs):
            return {"action": "PASS", "text": kwargs.get("text", "")}

        async def audit_event(self, **kwargs):
            return None

    monkeypatch.setattr(routes, "get_filter_client", lambda: MockFilter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: MockLLM())

    user = User(id="admin-1", name="Admin", email="admin@example.com", roles=["admin"], authenticated=True)
    req = ChatRequest(text="Dame el reporte mensual de facturación", user=user)

    resp = asyncio.run(routes.chat(req))
    print("TEST 2 RESP:", resp.blocked, resp.reason, resp.reply)
    make_doc_executions = [e for e in executions if e[0] == "make_document"]
    assert len(make_doc_executions) == 2, f"Expected 2 executions for different arguments, got {len(make_doc_executions)}"
    attachments = [a for a in resp.actions if a.get("type") == "attachment"]
    assert len(attachments) == 2


def test_tool_deduplication_different_users_do_not_share_cache(monkeypatch):
    """Different users or calls in separate requests do not share cache."""
    executions = []
    real_executor = routes.get_mcp_executor()
    orig_execute = real_executor.execute

    async def wrapped_execute(name, args, roles, authenticated=True):
        executions.append((name, args))
        return await orig_execute(name, args, roles, authenticated=authenticated)

    monkeypatch.setattr(real_executor, "execute", wrapped_execute)

    class MockLLM:
        def __init__(self):
            self.turn = 0

        async def generate_tool_turn(self, messages, tools, model_id=None, deadline=None):
            self.turn += 1
            if self.turn in (1, 3):
                return {
                    "model_id": "test",
                    "model": "test",
                    "provider": "openai",
                    "text": "",
                    "calls": [{
                        "id": f"c_{self.turn}",
                        "name": "make_document",
                        "arguments": json.dumps({"title": "reporte", "content": "Resumen autorizado", "format": "txt"}),
                    }],
                }
            return {"model_id": "test", "model": "test", "provider": "openai", "text": "Listo.", "calls": []}

    class MockFilter:
        async def filter_prompt(self, **kwargs):
            return SimpleNamespace(
                blocked=False,
                classification="BENIGN",
                layers={"conversation": {"message_count": len(kwargs.get("messages") or []), "blocked": False}},
                reason="",
                confidence=0.1,
            )

        async def output_guard(self, **kwargs):
            return {"action": "PASS", "text": kwargs.get("text", "")}

        async def audit_event(self, **kwargs):
            return None

    monkeypatch.setattr(routes, "get_filter_client", lambda: MockFilter())
    monkeypatch.setattr(routes, "get_llm_client", lambda: MockLLM())

    user1 = User(id="user-1", name="User 1", email="u1@example.com", roles=["admin"], authenticated=True)
    user2 = User(id="user-2", name="User 2", email="u2@example.com", roles=["admin"], authenticated=True)

    resp1 = asyncio.run(routes.chat(ChatRequest(text="Dame el reporte mensual de facturación", user=user1)))
    resp2 = asyncio.run(routes.chat(ChatRequest(text="Dame el reporte mensual de facturación", user=user2)))

    # Both requests executed their own tool call
    make_doc_executions = [e for e in executions if e[0] == "make_document"]
    assert len(make_doc_executions) == 2
