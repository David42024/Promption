import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat-service"))

import asyncio
import pytest
import httpx

from app.http_client import (
    create_shared_http_client,
    get_shared_http_client,
    set_shared_http_client,
    close_shared_http_client,
)
from app.llm_client import LLMClient
from app.deadline import RequestDeadline


@pytest.mark.asyncio
async def test_shared_client_reused_across_multiple_calls():
    calls = []

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            calls.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=request)

    mock_client = create_shared_http_client(transport=MockTransport())
    set_shared_http_client(mock_client)

    try:
        client1 = get_shared_http_client()
        client2 = get_shared_http_client()
        assert client1 is client2
        assert client1 is mock_client

        llm = LLMClient()
        llm.models = [{
            "id": "m1", "label": "M1", "provider": "openai", "api": "openai",
            "model": "gpt-4", "api_key": "k", "base_url": "https://api.openai.com/v1",
            "temperature": 0.2, "max_tokens": 50,
        }]

        res1 = await llm.generate([{"role": "user", "content": "hola"}], deadline=RequestDeadline(5.0))
        res2 = await llm.generate([{"role": "user", "content": "mundo"}], deadline=RequestDeadline(5.0))

        assert res1.ok and res2.ok
        assert len(calls) == 2
        # Verify the underlying client remained open and healthy
        assert not mock_client.is_closed
    finally:
        await close_shared_http_client()


@pytest.mark.asyncio
async def test_shared_client_closed_on_shutdown():
    mock_client = create_shared_http_client()
    set_shared_http_client(mock_client)
    assert not mock_client.is_closed

    await close_shared_http_client()
    assert mock_client.is_closed
    # After closure, get_shared_http_client returns a fresh client
    fresh = get_shared_http_client()
    assert fresh is not mock_client
    assert not fresh.is_closed
    await close_shared_http_client()


@pytest.mark.asyncio
async def test_concurrent_requests_with_distinct_identities_do_not_contaminate():
    user_headers_received = []

    class IdentityTrackingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            user_headers_received.append((request.headers.get("Authorization"), request.url.path))
            await asyncio.sleep(0.02)
            return httpx.Response(200, json={"choices": [{"message": {"content": "echo"}}]}, request=request)

    mock_client = create_shared_http_client(transport=IdentityTrackingTransport())
    set_shared_http_client(mock_client)

    try:
        llm1 = LLMClient()
        llm1.models = [{
            "id": "m1", "label": "M1", "provider": "openai", "api": "openai",
            "model": "gpt-4", "api_key": "key-alice", "base_url": "https://api.openai.com/v1",
            "temperature": 0.2, "max_tokens": 50,
        }]

        llm2 = LLMClient()
        llm2.models = [{
            "id": "m2", "label": "M2", "provider": "openai", "api": "openai",
            "model": "gpt-4", "api_key": "key-bob", "base_url": "https://api.openai.com/v1",
            "temperature": 0.2, "max_tokens": 50,
        }]

        res1, res2 = await asyncio.gather(
            llm1.generate([{"role": "user", "content": "alice request"}], deadline=RequestDeadline(5.0)),
            llm2.generate([{"role": "user", "content": "bob request"}], deadline=RequestDeadline(5.0)),
        )

        assert res1.ok and res2.ok
        auth_headers = [h[0] for h in user_headers_received]
        assert "Bearer key-alice" in auth_headers
        assert "Bearer key-bob" in auth_headers
        assert len(user_headers_received) == 2
    finally:
        await close_shared_http_client()


@pytest.mark.asyncio
async def test_cancellation_does_not_corrupt_client_for_subsequent_requests():
    call_idx = 0

    class CancelRecoveryTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                await asyncio.sleep(1.0)  # Will be cancelled
            return httpx.Response(200, json={"choices": [{"message": {"content": "recovered"}}]}, request=request)

    mock_client = create_shared_http_client(transport=CancelRecoveryTransport())
    set_shared_http_client(mock_client)

    try:
        llm = LLMClient()
        llm.models = [{
            "id": "m1", "label": "M1", "provider": "openai", "api": "openai",
            "model": "gpt-4", "api_key": "k", "base_url": "https://api.openai.com/v1",
            "temperature": 0.2, "max_tokens": 50,
        }]

        # Cancel request 1
        task = asyncio.create_task(llm.generate([{"role": "user", "content": "c1"}], deadline=RequestDeadline(2.0)))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Client must remain reusable for request 2
        res = await llm.generate([{"role": "user", "content": "c2"}], deadline=RequestDeadline(2.0))
        assert res.ok
        assert res.text == "recovered"
        assert not mock_client.is_closed
    finally:
        await close_shared_http_client()


@pytest.mark.asyncio
async def test_connection_limits_and_controlled_saturation():
    # Verifies limits configuration on shared client
    client = create_shared_http_client(
        max_connections=2,
        max_keepalive_connections=1,
        pool_timeout=0.05,
    )
    assert getattr(client._transport, "_pool", None)._max_connections == 2
    await client.aclose()
