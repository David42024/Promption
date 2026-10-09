"""Exercise HTTP-to-client-to-chat consumption boundaries without network calls."""
import asyncio
import httpx
import pytest

from test_defect_b_and_c_metrics import MockFilter, _make_req
from app import routes
from app.llm_client import LLMClient


pytestmark = pytest.mark.usefixtures("scope_in_scope")


def _model(name):
    return {"id": name, "label": name, "provider": "openai", "api": "vercel_ai",
            "model": name, "base_url": "https://bridge.invalid/turn", "max_tokens": 100,
            "temperature": 0.2}


def _partial_packet():
    return {"text": "Respuesta pública", "calls": [], "provider_calls": 2,
            "scope_calls": 1, "generation_calls": 1, "failed_calls": 0,
            "usage": {"prompt_tokens": None, "completion_tokens": None,
                      "total_tokens": None, "reasoning_tokens": None},
            "known_usage": {"prompt_tokens": 20, "completion_tokens": 10,
                            "total_tokens": 30, "reasoning_tokens": 0},
            "usage_coverage": {"calls_total": 2, "calls_with_usage": 1,
                               "calls_without_usage": 1, "is_complete": False,
                               "fields": {k: False for k in ("prompt_tokens", "completion_tokens",
                                                            "total_tokens", "reasoning_tokens")}}}


@pytest.mark.asyncio
@pytest.mark.parametrize("tools", [False, True])
async def test_bridge_partial_summary_survives_client_and_chat(monkeypatch, tools):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_partial_packet()))) as transport:
        llm = LLMClient(client=transport)
        llm.models = [_model("primary")]
        monkeypatch.setattr(routes, "get_llm_client", lambda: llm)
        monkeypatch.setattr(routes, "get_filter_client", lambda: MockFilter())
        if not tools:
            monkeypatch.setattr(routes, "capabilities", lambda *args, **kwargs: [])
        response = await routes.chat(_make_req("Muéstrame las categorías de productos de la tienda."))
    assert response.blocked is False
    metrics = response.execution_metrics
    assert metrics["provider_calls"] == 2
    assert metrics["scope_calls"] == 1
    assert metrics["generation_calls"] == 1
    assert metrics["total_tokens"] is None
    assert metrics["known_usage"]["total_tokens"] == 30
    assert metrics["usage_coverage"]["calls_with_usage"] == 1
    assert metrics["usage_coverage"]["calls_without_usage"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tools", [False, True])
async def test_invalid_success_before_fallback_counts_as_failed(tools):
    attempts = []

    def respond(request):
        attempts.append(request)
        text = "" if len(attempts) == 1 else "Respuesta pública"
        return httpx.Response(200, json={"text": text, "calls": [], "provider_calls": 1,
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        llm = LLMClient(client=transport)
        llm.models = [_model("primary"), _model("fallback")]
        llm.max_attempts = 1
        result = await llm.generate_tool_turn([], []) if tools else await llm.generate([])
    get = result.get if tools else lambda key: getattr(result, key)
    assert get("provider_calls") == 2
    assert get("failed_calls") == 1
    assert get("known_usage")["total_tokens"] == 6


@pytest.mark.asyncio
async def test_cancelled_transport_preserves_initiated_unknown_call():
    started = asyncio.Event()

    async def respond(request):
        started.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        llm = LLMClient(client=transport)
        llm.models = [_model("primary")]
        task = asyncio.create_task(llm.generate([]))
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as cancelled:
            await task
    assert cancelled.value.provider_calls == 1
    assert cancelled.value.failed_calls == 1
    assert cancelled.value.total_tokens is None
    assert cancelled.value.usage_coverage["calls_without_usage"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tools", [False, True])
async def test_security_error_preserves_remote_scope_summary(monkeypatch, tools):
    packet = {**_partial_packet(), "code": "CONTENT_BLOCKED", "failed_calls": 1}
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(403, json=packet))) as transport:
        llm = LLMClient(client=transport)
        llm.models = [_model("primary"), _model("unused-fallback")]
        monkeypatch.setattr(routes, "get_llm_client", lambda: llm)
        monkeypatch.setattr(routes, "get_filter_client", lambda: MockFilter())
        if not tools:
            monkeypatch.setattr(routes, "capabilities", lambda *args, **kwargs: [])
        response = await routes.chat(_make_req("Muéstrame las categorías de productos de la tienda."))
    assert response.blocked is True
    assert response.reason == "content_blocked"
    metrics = response.execution_metrics
    assert metrics["provider_calls"] == 2
    assert metrics["scope_calls"] == 1
    assert metrics["generation_calls"] == 1
    assert metrics["failed_calls"] == 1
    assert metrics["known_usage"]["total_tokens"] == 30
    assert metrics["total_tokens"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("tools", [False, True])
async def test_final_failure_carries_each_unknown_attempt(tools):
    from promption.llm.exceptions import LLMProviderUnavailableError

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
            httpx.Response(503, json={"provider_calls": 1}))) as transport:
        llm = LLMClient(client=transport)
        llm.models = [_model("primary"), _model("fallback")]
        llm.max_attempts = 1
        with pytest.raises(LLMProviderUnavailableError) as failure:
            if tools:
                await llm.generate_tool_turn([], [])
            else:
                await llm.generate([])
    assert failure.value.provider_calls == 2
    assert failure.value.failed_calls == 2
    assert len(failure.value.usage_events) == 2
    assert failure.value.usage_coverage["calls_without_usage"] == 2
    assert failure.value.total_tokens is None


def test_remote_summary_combines_with_local_usage_and_deduplicates():
    from promption.metrics_aggregator import MetricsAggregator

    packet = _partial_packet()
    aggregator = MetricsAggregator()
    assert aggregator.add_summary(packet, "remote") is True
    assert aggregator.add_summary(packet, "remote") is False
    aggregator.add_call("scope", calls=1, prompt_tokens=10, completion_tokens=5,
                        total_tokens=15, reasoning_tokens=0)
    summary = aggregator.summary()
    assert summary["provider_calls"] == 3
    assert summary["scope_calls"] == 2
    assert summary["generation_calls"] == 1
    assert summary["known_usage"]["total_tokens"] == 45
    assert summary["total_tokens"] is None
    assert summary["usage_coverage"]["calls_with_usage"] == 2
    assert summary["usage_coverage"]["calls_without_usage"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tools", [False, True])
async def test_failed_fallback_keeps_unknown_attempt_and_failure(monkeypatch, tools):
    attempts = []

    def respond(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503, json={"provider_calls": 1, "generation_calls": 1,
                                            "scope_calls": 0, "code": "MODEL_UNAVAILABLE"})
        return httpx.Response(200, json={"text": "Respuesta pública", "calls": [],
            "provider_calls": 1, "generation_calls": 1, "scope_calls": 0,
            "usage": {"prompt_tokens": 20, "completion_tokens": 10,
                      "total_tokens": 30, "reasoning_tokens": 0}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        llm = LLMClient(client=transport)
        llm.models = [_model("primary"), _model("fallback")]
        llm.max_attempts = 1
        monkeypatch.setattr(routes, "get_llm_client", lambda: llm)
        monkeypatch.setattr(routes, "get_filter_client", lambda: MockFilter())
        if not tools:
            monkeypatch.setattr(routes, "capabilities", lambda *args, **kwargs: [])
        response = await routes.chat(_make_req("Muéstrame las categorías de productos de la tienda."))
    assert len(attempts) == 2
    metrics = response.execution_metrics
    assert metrics["provider_calls"] == 2
    assert metrics["generation_calls"] == 2
    assert metrics["failed_calls"] == 1
    assert metrics["total_tokens"] is None
    assert metrics["known_usage"]["total_tokens"] == 30
    assert metrics["usage_coverage"]["calls_with_usage"] == 1
    assert metrics["usage_coverage"]["calls_without_usage"] == 1
