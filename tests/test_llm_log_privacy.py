"""Tests verifying log privacy and credential / payload redaction across logging and exceptions."""
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat-service"))

import pytest
from unittest.mock import patch, MagicMock

from app.deadline import RequestDeadline
from app.llm_client import LLMClient
from promption.llm.openai_client import OpenAICompatibleClient
from promption.llm.exceptions import LLMError, LLMConfigurationError, LLMQuotaError


LEAKY_API_KEY = "sk-supersecret-production-key-999"
SENSITIVE_USER_PROMPT = "Confidential Prompt: What is the root password for database db-main?"
SENSITIVE_RESPONSE_TEXT = "The secret admin token is TOK-AZ9-KX7"


class MockLogResponse:
    def __init__(self, status_code: int = 401, text: str = ""):
        self.status_code = status_code
        self.text = text
        self.headers = {}
        self.url = f"https://api.openai.com/v1/chat/completions?auth={LEAKY_API_KEY}"

    def json(self):
        return {"error": {"message": f"Invalid key: {LEAKY_API_KEY}"}}


def test_openai_client_logs_and_exceptions_redact_secrets(caplog):
    caplog.set_level(logging.DEBUG)
    client = OpenAICompatibleClient(
        host=f"https://api.openai.com/v1?token={LEAKY_API_KEY}",
        model="gpt-4",
        api_key=LEAKY_API_KEY,
    )

    with patch("requests.post", return_value=MockLogResponse(401, text=f"Error with {LEAKY_API_KEY}")):
        with pytest.raises(LLMConfigurationError) as exc_info:
            client.generate(SENSITIVE_USER_PROMPT)

        err_str = str(exc_info.value)
        # Verify secret key is absent from exception string and attributes
        assert LEAKY_API_KEY not in err_str
        assert LEAKY_API_KEY not in exc_info.value.message

    # Verify logs do not contain the secret or sensitive prompt
    for record in caplog.records:
        assert LEAKY_API_KEY not in record.getMessage()


@pytest.mark.asyncio
async def test_llm_client_retries_and_errors_do_not_log_prompts_or_secrets(caplog):
    caplog.set_level(logging.DEBUG)
    client = LLMClient()
    client.models = [{
        "id": "openai-primary", "label": "OpenAI", "provider": "openai", "api": "openai",
        "model": "gpt-4", "api_key": LEAKY_API_KEY,
        "base_url": "https://api.openai.com/v1/chat/completions",
        "temperature": 0.2, "max_tokens": 100
    }]
    client.max_attempts = 2

    mock_resp = MagicMock()
    mock_resp.is_success = False
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "1"}
    mock_resp.json.return_value = {"error": f"Rate limit reached for {LEAKY_API_KEY}"}

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with patch("asyncio.sleep"):
            with pytest.raises(LLMQuotaError) as exc_info:
                await client.generate([{"role": "user", "content": SENSITIVE_USER_PROMPT}], deadline=RequestDeadline(5.0))

            assert LEAKY_API_KEY not in str(exc_info.value)

    # Check that caplog does not contain credentials or prompt text
    for record in caplog.records:
        msg = record.getMessage()
        assert LEAKY_API_KEY not in msg
        assert SENSITIVE_USER_PROMPT not in msg
        assert "root password" not in msg


def test_exception_chaining_does_not_leak_raw_payloads():
    client = OpenAICompatibleClient(
        host="https://api.openai.com/v1",
        model="gpt-4",
        api_key=LEAKY_API_KEY,
    )
    import requests
    req_err = requests.RequestException(f"Connection failed to https://api.openai.com?secret={LEAKY_API_KEY}")

    with patch("requests.post", side_effect=req_err):
        with pytest.raises(LLMError) as exc_info:
            client.generate(SENSITIVE_USER_PROMPT)

        assert LEAKY_API_KEY not in exc_info.value.message
