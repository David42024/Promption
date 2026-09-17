from src.llm.openai_client import OpenAICompatibleClient


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 1,
                "total_tokens": 72,
            },
        }


def test_openai_compatible_client_captures_hidden_reasoning_tokens(monkeypatch):
    monkeypatch.setattr("src.llm.openai_client.requests.post", lambda *args, **kwargs: _Response())
    client = OpenAICompatibleClient(
        host="https://example.test/v1",
        model="test-model",
        api_key="test-key",
    )

    response = client.generate("hello")

    assert response.input_tokens == 15
    assert response.output_tokens == 1
    assert response.reasoning_tokens == 56
    assert response.total_tokens == 72
