"""Deterministic HTTP-mock tests. No external provider calls."""
import pytest
from unittest.mock import patch
from promption.llm.openai_client import OpenAICompatibleClient
from promption.llm.exceptions import LLMInvalidResponseError


class Response:
    status_code = 200
    def __init__(self, content, finish_reason="stop", usage=None):
        self._content = content
        self._finish = finish_reason
        self._usage = usage or {}
    def json(self):
        return {"choices": [{"finish_reason": self._finish, "message": {"content": self._content}}],
                "usage": self._usage}


def test_gpt5_uses_reasoning_aware_default_budget():
    received = []
    def fake_post(*args, **kwargs):
        received.append(kwargs["json"])
        return Response("Hola", usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16})
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="gpt-5-nano", api_key="sk-test")
    with patch("requests.post", side_effect=fake_post):
        r = client.generate("hola")
    assert received[0]["max_completion_tokens"] >= 768
    assert r.text == "Hola" and r.provider_calls == 1 and r.retry_count == 0


def test_empty_length_limited_gpt5_retries_once_and_counts_usage():
    received = []
    def fake_post(*args, **kwargs):
        received.append(kwargs["json"].copy())
        if len(received) == 1:
            return Response(None, "length", {"prompt_tokens": 30, "completion_tokens": 768, "total_tokens": 798,
                                              "completion_tokens_details": {"reasoning_tokens": 768}})
        return Response("Respuesta final", "stop", {"prompt_tokens": 30, "completion_tokens": 30, "total_tokens": 60})
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="gpt-5-nano", api_key="sk-test")
    with patch("requests.post", side_effect=fake_post):
        r = client.generate("consulta")
    assert len(received) == 2
    assert received[1]["max_completion_tokens"] > received[0]["max_completion_tokens"]
    assert r.provider_calls == 2 and r.retry_count == 1
    assert r.total_tokens == 858 and r.reasoning_tokens is None
    assert r.known_usage["reasoning"] == 768
    assert r.text == "Respuesta final"


def test_explicit_token_limit_is_respected_and_not_retried():
    received = []
    def fake_post(*args, **kwargs):
        received.append(kwargs["json"])
        return Response(None, "length")
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="gpt-5-nano", api_key="sk-test")
    with patch("requests.post", side_effect=fake_post):
        with pytest.raises(LLMInvalidResponseError) as exc_info:
            client.generate("consulta", max_tokens=100)
    assert len(received) == 1 and received[0]["max_completion_tokens"] == 100
    assert exc_info.value.provider_calls == 1


def test_no_retry_for_empty_non_length_response():
    call = []
    def fake_post(*args, **kwargs):
        call.append(1)
        return Response("", "content_filter")
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="gpt-5-nano", api_key="sk-test")
    with patch("requests.post", side_effect=fake_post):
        with pytest.raises(LLMInvalidResponseError):
            client.generate("consulta")
    assert len(call) == 1


def test_other_providers_keep_original_limit_and_do_not_retry():
    received = []
    def fake_post(*args, **kwargs):
        received.append(kwargs["json"])
        return Response("OK")
    client = OpenAICompatibleClient(host="https://example.test/v1", model="test-model", api_key="sk-test")
    with patch("requests.post", side_effect=fake_post):
        r = client.generate("consulta")
    assert r.text == "OK" and len(received) == 1
    assert received[0]["max_tokens"] == 200


def test_empty_after_retry_raises_instead_of_fabricating_a_response():
    received = []
    def fake_post(*args, **kwargs):
        received.append(kwargs["json"])
        return Response("", "length")
    client = OpenAICompatibleClient(host="https://api.openai.com/v1", model="gpt-5-nano", api_key="sk-test")
    with patch("requests.post", side_effect=fake_post):
        with pytest.raises(LLMInvalidResponseError) as e:
            client.generate("consulta")
    assert len(received) == 2 and e.value.provider_calls == 2
