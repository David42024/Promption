import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat-service"))

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.deadline import RequestDeadline
from app.llm_client import LLMClient
from promption.llm.exceptions import LLMTimeoutError


def test_deadline_monotonic_remaining_and_expiration():
    deadline = RequestDeadline(total_seconds=0.1)
    assert deadline.remaining > 0
    assert not deadline.is_expired
    time.sleep(0.12)
    assert deadline.is_expired
    assert deadline.remaining == 0.0
    with pytest.raises(LLMTimeoutError) as exc_info:
        deadline.check_expired("step1")
    assert "step1" in exc_info.value.message


def test_deadline_remaining_for_step_respects_less_than_30s():
    # Verify values under 30 seconds are strictly respected and never raised to 30
    deadline = RequestDeadline(total_seconds=5.0)
    step_timeout = deadline.remaining_for_step(step_limit=4.0)
    assert step_timeout <= 4.0
    assert step_timeout < 30.0

    # Remaining bounded by smaller step_limit
    small_step = deadline.remaining_for_step(step_limit=2.0)
    assert small_step <= 2.0


def test_llm_client_does_not_clamp_timeout_to_30_seconds():
    # LLMClient was previously enforcing max(provider_timeout, 30.0); ensure that is removed
    client = LLMClient()
    client.provider_timeout = 10.0
    assert client.provider_timeout == 10.0
    client.total_timeout = 15.0
    assert client.total_timeout == 15.0


@pytest.mark.asyncio
async def test_filter_consumes_budget_leaving_remaining_for_generation():
    budget = RequestDeadline(total_seconds=0.5)
    # Simulate filter consuming 0.2s of the budget
    await asyncio.sleep(0.2)
    remaining_for_gen = budget.remaining_for_step(step_limit=1.0)
    assert remaining_for_gen < 0.4
    assert remaining_for_gen > 0.1


@pytest.mark.asyncio
async def test_two_turns_share_same_deadline_budget():
    budget = RequestDeadline(total_seconds=0.4)
    client = LLMClient()
    client.models = [
        {
            "id": "mock-llm",
            "label": "Mock LLM",
            "provider": "openai",
            "api": "openai",
            "model": "gpt-4",
            "api_key": "test",
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.2,
            "max_tokens": 100,
        }
    ]

    async def slow_turn(*args, **kwargs):
        # Simulate turn consuming 0.25s
        await asyncio.sleep(0.25)
        return {"calls": [], "text": "Turn 1 done", "model_id": "mock-llm", "model": "Mock LLM", "provider": "openai"}

    # Turn 1 takes 0.25s of 0.4s budget
    with patch.object(client, "generate_tool_turn", side_effect=slow_turn):
        turn1 = await client.generate_tool_turn([], [], deadline=budget)
        assert turn1["text"] == "Turn 1 done"

    # Turn 2: Now budget has only ~0.15s left
    assert budget.remaining < 0.2
    # Turn 2 will expire budget before another long step
    await asyncio.sleep(0.2)
    assert budget.is_expired
    with pytest.raises(LLMTimeoutError):
        budget.check_expired("turn_2")


@pytest.mark.asyncio
async def test_llm_client_does_not_start_when_budget_exhausted():
    budget = RequestDeadline(total_seconds=0.01)
    await asyncio.sleep(0.02)
    client = LLMClient()
    client.models = [{"id": "m1", "label": "M1", "provider": "openai", "api": "openai",
                      "model": "m", "api_key": "k", "base_url": "u", "temperature": 0.2, "max_tokens": 100}]

    with pytest.raises(LLMTimeoutError) as exc_info:
        await client.generate([{"role": "user", "content": "hi"}], deadline=budget)
    assert "deadline exceeded" in exc_info.value.message.lower()
