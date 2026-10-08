"""Configuration and fixtures for opt-in live LLM integration tests."""
import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CHAT_DIR = ROOT / "chat-service"
if str(CHAT_DIR) not in sys.path:
    sys.path.insert(0, str(CHAT_DIR))


def pytest_collection_modifyitems(config, items):
    """Skip items marked live_llm unless explicitly enabled via environment variable."""
    run_live = os.getenv("PROMPTION_RUN_LIVE_TESTS") == "1"
    for item in items:
        if "live_llm" in item.keywords and not run_live:
            item.add_marker(pytest.mark.skip(reason="Live LLM tests are opt-in (set PROMPTION_RUN_LIVE_TESTS=1)"))


@pytest.fixture(scope="session")
def live_llm_config():
    """Validates presence of live LLM test configuration or skips if missing."""
    run_live = os.getenv("PROMPTION_RUN_LIVE_TESTS") == "1"
    if not run_live:
        pytest.skip("PROMPTION_RUN_LIVE_TESTS is not set to '1'")

    from app.config import settings
    # Ensure there is at least one valid configured key or url
    has_provider = bool(
        os.getenv("OPENAI_API_KEY") or settings.gemini_api_key or settings.groq_api_key or settings.openrouter_api_key or settings.vercel_ai_url
    )
    if not has_provider:
        pytest.fail("PROMPTION_RUN_LIVE_TESTS=1 was requested, but no live LLM provider credentials are configured in the environment")
    return settings
