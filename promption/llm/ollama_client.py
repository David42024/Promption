"""Thin client for Ollama's HTTP API (works with or without the ``ollama`` SDK)."""
from __future__ import annotations

from dataclasses import dataclass

import requests

from promption.llm.exceptions import (
    LLMConfigurationError,
    LLMConnectivityError,
    LLMInvalidResponseError,
    LLMProviderUnavailableError,
    LLMTimeoutError,
)
from promption.utils.config import load_config
from promption.utils.logger import logger

_CONF = load_config().get("llm", {})


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: float
    ok: bool = True
    truncated: bool = False
    error: str | None = None
    finish_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            self.ok = False
            if not self.error:
                self.error = "empty response"


class OllamaClient:
    def __init__(self, host: str | None = None, model: str | None = None, timeout: int | None = None):
        self.host = (host or _CONF.get("host", "http://localhost:11434")).rstrip("/")
        self.model = model or _CONF.get("model", "llama3.2")
        self.timeout = timeout or int(_CONF.get("timeout", 60))
        self.health_timeout = int(_CONF.get("health_timeout", 5))

    # ------------------------------------------------------------------ status
    def health(self) -> dict:
        try:
            models = self.list_models()
            return {
                "connected": True,
                "host": self.host,
                "models": models,
                "default_model": self.model,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "connected": False,
                "host": self.host,
                "models": [],
                "default_model": self.model,
                "error": str(exc),
            }

    def list_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=self.health_timeout)
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(f"Ollama tags request timed out after {self.health_timeout}s",
                                  model=self.model, provider="ollama") from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectivityError("Cannot connect to Ollama daemon",
                                      model=self.model, provider="ollama") from exc
        except requests.RequestException as exc:
            raise LLMConnectivityError(f"Ollama request error: {type(exc).__name__}",
                                      model=self.model, provider="ollama") from exc

        if r.status_code != 200:
            if r.status_code >= 500:
                raise LLMProviderUnavailableError(f"Ollama returned {r.status_code}",
                                                  model=self.model, provider="ollama", status_code=r.status_code)
            raise LLMConfigurationError(f"Ollama returned {r.status_code}",
                                        model=self.model, provider="ollama", status_code=r.status_code)
        try:
            data = r.json()
        except Exception as exc:
            raise LLMInvalidResponseError("Ollama tags response is not valid JSON",
                                          model=self.model, provider="ollama") from exc
        return [m["name"] for m in data.get("models", []) if isinstance(m, dict) and "name" in m]

    # ----------------------------------------------------------------- generate
    def generate(self, prompt: str, system: str | None = None, temperature: float | None = None,
                 max_tokens: int | None = None) -> LLMResponse:
        import time

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else float(_CONF.get("temperature", 0.2)),
                "num_predict": max_tokens if max_tokens is not None else int(_CONF.get("max_tokens", 200)),
            },
        }
        if system:
            payload["system"] = system

        start = time.perf_counter()
        try:
            r = requests.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(f"Ollama request timed out after {self.timeout}s",
                                  model=self.model, provider="ollama") from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectivityError("Cannot connect to Ollama daemon",
                                      model=self.model, provider="ollama") from exc
        except requests.RequestException as exc:
            raise LLMConnectivityError(f"Ollama network error: {type(exc).__name__}",
                                      model=self.model, provider="ollama") from exc

        if r.status_code != 200:
            if r.status_code == 404:
                raise LLMConfigurationError(f"Ollama model '{self.model}' not found",
                                            model=self.model, provider="ollama", status_code=404)
            if r.status_code >= 500:
                raise LLMProviderUnavailableError(f"Ollama server error {r.status_code}",
                                                  model=self.model, provider="ollama", status_code=r.status_code)
            raise LLMConfigurationError(f"Ollama error {r.status_code}",
                                        model=self.model, provider="ollama", status_code=r.status_code)

        try:
            data = r.json()
        except Exception as exc:
            raise LLMInvalidResponseError("Ollama response is not valid JSON",
                                          model=self.model, provider="ollama") from exc

        if not isinstance(data, dict):
            raise LLMInvalidResponseError("Ollama response must be a JSON object",
                                          model=self.model, provider="ollama")

        content = data.get("response")
        if not isinstance(content, str) or not content.strip():
            raise LLMInvalidResponseError("Ollama returned empty response",
                                          model=self.model, provider="ollama")

        finish_reason = data.get("done_reason")
        truncated = (finish_reason == "length") or (data.get("done") is False)

        latency = (time.perf_counter() - start) * 1000
        logger.debug("LLM call: %s chars in %.1fms", len(content), latency)
        input_tokens = int(data.get("prompt_eval_count") or 0)
        output_tokens = int(data.get("eval_count") or 0)
        return LLMResponse(
            text=content,
            model=self.model,
            latency_ms=latency,
            ok=True,
            truncated=truncated,
            finish_reason=str(finish_reason) if finish_reason else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )


if __name__ == "__main__":
    c = OllamaClient()
    print("health:", c.health())
    if c.health()["connected"]:
        resp = c.generate("Di hola en español")
        print("resp:", resp.text[:200])
