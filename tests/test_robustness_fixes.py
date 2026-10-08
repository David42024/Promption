"""Tests reproducing and validating the four robustness fixes:
1. /health and /status endpoints work via HTTP and LLMClient.check_health() exists.
2. The deadline budget strictly caps total duration, even with slow/trickling servers.
3. Startup rejects incomplete filter and LLM configuration outside test mode.
4. Benchmark RunnerOptions accepts results_dir, metrics expose n_total, and test samples are genuine.
"""
import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CHAT_DIR = ROOT / "chat-service"
if str(CHAT_DIR) not in sys.path:
    sys.path.insert(0, str(CHAT_DIR))

from app.main import app
from app.config import Settings, validate_chat_service_configuration
from app.deadline import RequestDeadline
from app.llm_client import LLMClient, get_llm_client
from app.models import ChatRequest, User, UserRole
from app import routes
from promption.benchmark.runner import BenchmarkRunner, RunnerOptions
from promption.benchmark.payloads import load_evaluation_set
from promption.llm.exceptions import LLMTimeoutError


def test_health_and_status_endpoints_via_http():
    """1. /health and /status must return HTTP 200 without AttributeError from check_health."""
    client = TestClient(app)
    
    # Test /api/v1/health
    resp_health = client.get("/api/v1/health")
    assert resp_health.status_code == 200
    data_health = resp_health.json()
    assert "status" in data_health
    assert "llm_connected" in data_health
    assert isinstance(data_health["llm_connected"], bool)

    # Test /api/v1/status
    resp_status = client.get("/api/v1/status")
    assert resp_status.status_code == 200
    data_status = resp_status.json()
    assert "llm" in data_status
    assert "connected" in data_status["llm"]
    assert isinstance(data_status["llm"]["connected"], bool)


@pytest.mark.asyncio
async def test_llm_client_check_health_direct():
    """1b. Direct call to llm_client.check_health() must succeed and return a bool."""
    client = get_llm_client()
    result = await client.check_health()
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_deadline_strictly_bounds_slow_trickling_server():
    """2. An LLM call with a 0.5s budget against a slow server taking 1.5s must be aborted by deadline."""
    client = LLMClient()
    client.models = [{
        "id": "mock-slow",
        "label": "Mock Slow Model",
        "provider": "openai",
        "api": "vercel_ai",
        "model": "gpt-mock",
        "base_url": "http://mock-slow-host/chat",
        "temperature": 0.2,
        "max_tokens": 100,
    }]

    async def slow_post(*args, **kwargs):
        # Simulates a slow socket trickling bytes that takes 1.5s
        await asyncio.sleep(1.5)
        mock_resp = AsyncMock()
        mock_resp.is_success = True
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"choices": [{"message": {"content": "respuesta tardía"}}]}
        return mock_resp

    t0 = time.monotonic()
    budget = RequestDeadline(total_seconds=0.5)

    with patch("httpx.AsyncClient.post", side_effect=slow_post):
        with pytest.raises(LLMTimeoutError):
            await client.generate([{"role": "user", "content": "hola"}], deadline=budget)

    elapsed = time.monotonic() - t0
    # Must have timed out close to 0.5s, well before the 1.5s slow response
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_chat_endpoint_strictly_bounds_total_budget():
    """2b. The chat endpoint wrapped in asyncio.timeout must return HTTP 504 if pipeline stalls."""
    from fastapi import HTTPException

    budget = RequestDeadline(total_seconds=0.4)
    req = ChatRequest(
        text="hola",
        user=User(id="u1", name="Test", email="test@example.com", roles=[UserRole.CUSTOMER], authenticated=True),
        context={"conversation_id": "conv-timeout-test"},
    )

    async def stalling_internal(*args, **kwargs):
        await asyncio.sleep(1.2)
        return routes.ChatResponse(reply="tarde")

    with patch.object(routes, "_chat_internal", side_effect=stalling_internal):
        t0 = time.monotonic()
        with pytest.raises(HTTPException) as exc_info:
            await routes.chat(req, deadline=budget)
        elapsed = time.monotonic() - t0

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail.get("code") == "GATEWAY_TIMEOUT"
        assert elapsed < 0.9


def test_startup_rejects_incomplete_configuration_outside_test_mode():
    """3. Startup outside test mode must reject missing filter or missing LLM provider."""
    # Case A: Only service token, no filter
    cfg_no_filter = Settings(
        chat_service_token="secret-token-123",
        filter_api_url="",
        llm_provider_order="openai",
    )
    with pytest.raises(ValueError, match="filter_api_url is required"):
        validate_chat_service_configuration(cfg_no_filter, is_test=False)

    # Case B: Filter configured, but OpenAI provider missing vercel_ai_url
    cfg_no_vercel = Settings(
        chat_service_token="secret-token-123",
        filter_api_url="https://filter.example.com",
        filter_api_key="test-filter-key",
        llm_provider_order="openai",
        vercel_ai_url="",
        openai_model="gpt-4o",
        openai_tool_model="gpt-4o-mini",
    )
    with pytest.raises(ValueError, match="vercel_ai_url"):
        validate_chat_service_configuration(cfg_no_vercel, is_test=False)

    # Case C: Filter configured, but Gemini provider missing gemini_api_key
    cfg_no_gemini = Settings(
        chat_service_token="secret-token-123",
        filter_api_url="https://filter.example.com",
        filter_api_key="test-filter-key",
        llm_provider_order="gemini",
        gemini_api_key=None,
    )
    with pytest.raises(ValueError, match="gemini_api_key"):
        validate_chat_service_configuration(cfg_no_gemini, is_test=False)

    # Case D: Complete configuration passes
    cfg_valid = Settings(
        chat_service_token="secret-token-123",
        filter_api_url="https://filter.example.com",
        filter_api_key="test-filter-key",
        llm_provider_order="gemini",
        gemini_api_key="AIzaSyTestKey123",
        gemini_model="gemini-2.0-flash",
    )
    validate_chat_service_configuration(cfg_valid, is_test=False)


def test_runner_options_results_dir_and_metrics_schema(tmp_path):
    """4. RunnerOptions accepts results_dir without TypeError, metrics expose n_total, and history stays isolated."""
    eval_set = load_evaluation_set(partition="test", allow_exploratory=False)
    assert len(eval_set) > 0
    # Must have authentic columns and labels from strict test partition
    assert "prompt" in eval_set.columns
    assert "label" in eval_set.columns

    attacks = eval_set[eval_set["label"] == 1].sample(n=1, random_state=42)
    benign = eval_set[eval_set["label"] == 0].sample(n=1, random_state=42)
    import pandas as pd
    sample_df = pd.concat([attacks, benign], ignore_index=True)
    assert len(sample_df) == 2

    custom_dir = tmp_path / "custom_results"
    opts = RunnerOptions(
        data=sample_df,
        use_llm=False,
        use_ml=False,
        save=True,
        results_dir=custom_dir,
    )
    assert opts.results_dir == custom_dir

    runner = BenchmarkRunner(opts=opts)
    out_df, metrics = runner.run()

    assert len(out_df) == 2
    assert "n_total" in metrics
    assert metrics["n_total"] == 2
    # Verify save honors custom_dir without touching official paths
    assert (custom_dir / "benchmark_results.csv").exists()
    assert (custom_dir / "benchmark_results_latest.json").exists()
    # Verify history was created inside custom_dir, keeping the run completely isolated
    assert (custom_dir / "history").is_dir()
    assert len(list((custom_dir / "history").glob("run_*.csv"))) > 0
