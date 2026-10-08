#!/usr/bin/env python3
"""Validation preflight script for live LLM integration.
Exit codes:
  0 = Approved / Passed
  1 = Failed
  2 = Inconclusive (e.g., credentials missing, provider unreachable, quota exhausted during preflight)
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root and chat-service to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CHAT_DIR = ROOT / "chat-service"
sys.path.insert(0, str(CHAT_DIR))

from app.config import settings
from app.llm_client import get_llm_client
from app.deadline import RequestDeadline
from promption.llm.exceptions import (
    LLMConfigurationError,
    LLMConnectivityError,
    LLMError,
    LLMQuotaError,
    LLMTimeoutError,
)

MAX_PREFLIGHT_CALLS = 5


def preflight_check() -> int:
    """Runs connectivity preflight, returns exit code."""
    print("=== Promption Live LLM Preflight ===")

    # 1. Check configuration
    has_keys = any([
        os.getenv("OPENAI_API_KEY"),
        settings.gemini_api_key,
        settings.groq_api_key,
        settings.openrouter_api_key,
        settings.vercel_ai_url,
    ])
    if not has_keys:
        print("[INCONCLUSIVE] No live LLM provider keys or URLs configured in environment.")
        print("  Set OPENAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, or VERCEL_AI_URL.")
        return 2

    # 2. Check provider reachability
    client = get_llm_client()
    if not client.models:
        print("[INCONCLUSIVE] No active models could be initialized.")
        return 2

    active_provider = client.models[0]["provider"]
    model_name = client.models[0]["label"]
    print(f"Targeting provider: {active_provider} ({model_name})")

    # 3. Perform a minimal ping call with strict deadline
    budget = RequestDeadline(15.0)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        test_messages = [{"role": "user", "content": "Ping"}]
        t0 = time.perf_counter()
        res = loop.run_until_complete(client.generate(test_messages, deadline=budget))
        elapsed_ms = (time.perf_counter() - t0) * 1000
    except (LLMConnectivityError, LLMTimeoutError) as exc:
        print(f"[INCONCLUSIVE] Provider unreachable: {exc.message}")
        return 2
    except LLMQuotaError as exc:
        print(f"[INCONCLUSIVE] Provider quota exceeded: {exc.message}")
        return 2
    except LLMConfigurationError as exc:
        print(f"[FAILED] Authentication or configuration rejected: {exc.message}")
        return 1
    except Exception as exc:
        print(f"[FAILED] Unexpected preflight failure: {type(exc).__name__}: {exc}")
        return 1

    if not res.ok or not res.text.strip():
        print("[FAILED] LLM returned empty response or ok=False.")
        return 1

    print(f"[APPROVED] Preflight successful in {elapsed_ms:.1f}ms. Model response received.")
    evidence_dir = ROOT / "data" / "results" / "validation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = evidence_dir / f"live_preflight_{int(time.time())}.json"
    evidence_file.write_text(
        json.dumps({
            "status": "APPROVED",
            "provider": active_provider,
            "model": model_name,
            "latency_ms": elapsed_ms,
            "timestamp": time.time(),
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Sanitized evidence saved to: {evidence_file}")
    return 0


if __name__ == "__main__":
    exit_code = preflight_check()
    sys.exit(exit_code)
