"""Tests for typed LLM provider errors, schema validation, and sanitization."""
import json
import pytest
from unittest.mock import MagicMock, patch

from promption.llm.exceptions import (
    LLMError,
    LLMConfigurationError,
    LLMTimeoutError,
    LLMConnectivityError,
    LLMQuotaError,
    LLMProviderUnavailableError,
    LLMInvalidResponseError,
    parse_retry_after,
)
from promption.llm.openai_client import OpenAICompatibleClient
from promption.llm.ollama_client import OllamaClient


SECRET_MARKER = "REAL_OR_FAKE_SECRET_KEY_XYZ_987"


class MockHttpResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or (json.dumps(json_data) if json_data is not None else "")
        self.headers = headers or {}

    def json(self):
        if self._json_data is not None:
            return self._json_data
        raise ValueError("Invalid JSON in mock response")


def test_openai_http_200_without_choices():
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="test-model", api_key="sk-test")
    resp = MockHttpResponse(200, json_data={"choices": []})
    with patch("requests.post", return_value=resp):
        with pytest.raises(LLMInvalidResponseError) as exc_info:
            client.generate("hello")
        assert "choices" in exc_info.value.message.lower()
        assert exc_info.value.status_code == 502


def test_openai_http_200_empty_content():
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="test-model", api_key="sk-test")
    resp = MockHttpResponse(200, json_data={"choices": [{"message": {"content": "   "}}]})
    with patch("requests.post", return_value=resp):
        with pytest.raises(LLMInvalidResponseError) as exc_info:
            client.generate("hello")
        assert "empty" in exc_info.value.message.lower()
        assert exc_info.value.status_code == 502


def test_openai_http_200_malformed_json():
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="test-model", api_key="sk-test")
    resp = MockHttpResponse(200, text="Not a valid json { broken")
    resp._json_data = None
    with patch("requests.post", return_value=resp):
        with pytest.raises(LLMInvalidResponseError) as exc_info:
            client.generate("hello")
        assert "json" in exc_info.value.message.lower()


def test_openai_http_200_invalid_payload_schema():
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="test-model", api_key="sk-test")
    resp = MockHttpResponse(200, json_data="not a dict, a string")
    with patch("requests.post", return_value=resp):
        with pytest.raises(LLMInvalidResponseError) as exc_info:
            client.generate("hello")


def test_openai_401_403_configuration_error_sanitizes_body():
    client = OpenAICompatibleClient(
        host="https://api.openai.com/v1",
        model="test-model",
        api_key=SECRET_MARKER,
    )
    raw_body = f'{{"error": "{SECRET_MARKER} is invalid"}}'
    resp = MockHttpResponse(401, text=raw_body, headers={})
    with patch("requests.post", return_value=resp):
        with pytest.raises(LLMConfigurationError) as exc_info:
            client.generate("hello")
        err = exc_info.value
        assert err.status_code == 401
        assert SECRET_MARKER not in str(err)
        assert SECRET_MARKER not in err.message


def test_openai_429_quota_error_with_retry_after():
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="test-model", api_key="sk-test")
    resp = MockHttpResponse(429, headers={"Retry-After": "45"})
    with patch("requests.post", return_value=resp):
        with pytest.raises(LLMQuotaError) as exc_info:
            client.generate("hello")
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 45.0


def test_openai_503_provider_unavailable():
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="test-model", api_key="sk-test")
    resp = MockHttpResponse(503, text="Service Temporarily Unavailable")
    with patch("requests.post", return_value=resp):
        with pytest.raises(LLMProviderUnavailableError) as exc_info:
            client.generate("hello")
        assert exc_info.value.status_code == 503


def test_openai_timeout_sanitizes_url_and_secret():
    client = OpenAICompatibleClient(
        host=f"https://api.openai.com/v1?token={SECRET_MARKER}",
        model="test-model",
        api_key="sk-test",
    )
    import requests
    with patch("requests.post", side_effect=requests.exceptions.Timeout("Connection timed out")):
        with pytest.raises(LLMTimeoutError) as exc_info:
            client.generate("hello")
        assert SECRET_MARKER not in str(exc_info.value)
        assert exc_info.value.status_code == 504


def test_openai_disconnect_connectivity_error():
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="test-model", api_key="sk-test")
    import requests
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Failed to establish a new connection")):
        with pytest.raises(LLMConnectivityError) as exc_info:
            client.generate("hello")
        assert exc_info.value.status_code == 503


def test_ollama_empty_response_not_ok():
    client = OllamaClient(host="http://localhost:11434", model="llama3")
    resp = MockHttpResponse(200, json_data={"response": "    "})
    with patch("requests.post", return_value=resp):
        with pytest.raises(LLMInvalidResponseError) as exc_info:
            client.generate("hello")
        assert exc_info.value.status_code == 502


def test_ollama_timeout_maps_to_typed_timeout():
    client = OllamaClient(host="http://localhost:11434", model="llama3")
    import requests
    with patch("requests.post", side_effect=requests.exceptions.Timeout("timed out")):
        with pytest.raises(LLMTimeoutError) as exc_info:
            client.generate("hello")
        assert exc_info.value.status_code == 504


def test_parse_retry_after_seconds_and_http_date():
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after("0") == 0.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("invalid-string") is None
    # HTTP-date in the future
    import email.utils
    import time
    future_time = time.time() + 60
    http_date = email.utils.formatdate(future_time, usegmt=True)
    parsed = parse_retry_after(http_date)
    assert parsed is not None
    assert 50.0 <= parsed <= 70.0
