"""Capa LLM: cliente OpenAI-compatible (Groq, OpenRouter, Gemini…) para entornos sin Ollama."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import requests

from promption.llm.exceptions import (
    LLMConfigurationError,
    LLMConnectivityError,
    LLMInvalidResponseError,
    LLMProviderUnavailableError,
    LLMQuotaError,
    LLMTimeoutError,
    parse_retry_after,
)
from promption.llm.ollama_client import LLMResponse
from promption.utils.config import load_config
from promption.utils.logger import logger

_CONF = load_config().get("llm", {})


def resolve_api_key() -> str | None:
    """Lee PIF_LLM_API_KEY desde la variable de entorno o de los secrets de Streamlit."""
    key = os.environ.get("PIF_LLM_API_KEY", "").strip()
    if key:
        return key
    try:
        import streamlit as st  # type: ignore
        try:
            val = st.secrets.get("PIF_LLM_API_KEY")
        except Exception:  # noqa: BLE001
            val = None
        if val:
            key = str(val).strip()
            if key:
                return key
    except Exception:  # noqa: BLE001
        pass
    return None


def _sanitize_url(url: str) -> str:
    """Strips query parameters and credentials from URLs for logging and exceptions."""
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
    except Exception:
        return url.split("?")[0]


def _raise_for_http_error(r: requests.Response, model: str) -> None:
    """Translates an HTTP error into a typed LLM exception with sanitized attributes (no raw body)."""
    status = getattr(r, "status_code", 500)
    clean_url = _sanitize_url(getattr(r, "url", ""))

    if status in (401, 403):
        raise LLMConfigurationError(
            f"Authentication failed (HTTP {status}) at {clean_url}",
            model=model,
            provider="openai",
            status_code=status,
        )
    if status == 429:
        retry_after = parse_retry_after(r.headers.get("Retry-After"))
        raise LLMQuotaError(
            f"Rate limit or quota exceeded (HTTP 429) at {clean_url}",
            model=model,
            provider="openai",
            retry_after=retry_after,
        )
    if status >= 500:
        raise LLMProviderUnavailableError(
            f"Provider unavailable (HTTP {status}) at {clean_url}",
            model=model,
            provider="openai",
            status_code=status,
        )
    if status in (400, 404):
        raise LLMConfigurationError(
            f"Invalid request or model not found (HTTP {status}) at {clean_url}",
            model=model,
            provider="openai",
            status_code=status,
        )
    raise LLMConfigurationError(
        f"Provider returned HTTP {status} at {clean_url}",
        model=model,
        provider="openai",
        status_code=status,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_setting(env_name: str) -> str:
    """Lee un ajuste desde el entorno o desde los secrets de Streamlit."""
    val = os.environ.get(env_name, "").strip()
    if val:
        return val
    try:
        import streamlit as st  # type: ignore
        try:
            secret = st.secrets.get(env_name)
        except Exception:  # noqa: BLE001
            secret = None
        if secret:
            return str(secret).strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


class OpenAICompatibleClient:
    """Cliente HTTP para APIs compatibles con OpenAI (POST /chat/completions).

    Configurable por variables de entorno o secrets de Streamlit:
      PIF_LLM_BASE_URL, PIF_LLM_MODEL, PIF_LLM_API_KEY
    """

    _DEFAULT_BASE = "https://api.groq.com/openai/v1"
    _DEFAULT_MODEL = "openai/gpt-oss-120b"

    def __init__(self, host: str | None = None, model: str | None = None,
                 timeout: int | None = None, api_key: str | None = None):
        openai = _CONF.get("openai", {})
        self.host = (host or _resolve_setting("PIF_LLM_BASE_URL") or openai.get("base_url")
                     or self._DEFAULT_BASE).rstrip("/")
        self.model = (model or _resolve_setting("PIF_LLM_MODEL") or openai.get("model")
                      or self._DEFAULT_MODEL)
        self.api_key = api_key or resolve_api_key()
        self.timeout = timeout or int(_CONF.get("timeout", 60))
        self.health_timeout = int(_CONF.get("health_timeout", 5))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def health(self) -> dict:
        try:
            models = self.list_models()
            return {"connected": True, "host": self.host, "models": models,
                    "default_model": self.model, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"connected": False, "host": self.host, "models": [], "default_model": self.model,
                    "error": str(exc)}

    def list_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.host}/models", headers=self._headers(), timeout=self.health_timeout)
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(f"Models request timed out after {self.health_timeout}s",
                                  model=self.model, provider="openai") from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectivityError("Cannot connect to provider models endpoint",
                                      model=self.model, provider="openai") from exc
        except requests.RequestException as exc:
            raise LLMConnectivityError(f"Models request error: {type(exc).__name__}",
                                      model=self.model, provider="openai") from exc

        if r.status_code != 200:
            _raise_for_http_error(r, self.model)

        try:
            data = r.json()
        except Exception as exc:
            raise LLMInvalidResponseError("Invalid JSON in models response",
                                          model=self.model, provider="openai") from exc

        if not isinstance(data, dict):
            raise LLMInvalidResponseError("Models response must be a JSON object",
                                          model=self.model, provider="openai")
        return [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]

    def generate(self, prompt: str, system: str | None = None, temperature: float | None = None,
                 max_tokens: int | None = None) -> LLMResponse:
        import time
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        is_openai_gpt5 = (
            "api.openai.com" in self.host.lower()
            and self.model.lower().startswith("gpt-5")
        )
        token_limit = max_tokens if max_tokens is not None else int(_CONF.get("max_tokens", 200))
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if is_openai_gpt5:
            payload["max_completion_tokens"] = token_limit
            payload["reasoning_effort"] = "minimal"
        else:
            payload["max_tokens"] = token_limit
            payload["temperature"] = (
                temperature if temperature is not None else float(_CONF.get("temperature", 0.2))
            )

        start = time.perf_counter()
        try:
            r = requests.post(f"{self.host}/chat/completions", json=payload,
                              headers=self._headers(), timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(f"Chat completion timed out after {self.timeout}s",
                                  model=self.model, provider="openai") from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectivityError("Cannot connect to chat completions endpoint",
                                      model=self.model, provider="openai") from exc
        except requests.RequestException as exc:
            raise LLMConnectivityError(f"Chat completion error: {type(exc).__name__}",
                                      model=self.model, provider="openai") from exc

        status = getattr(r, "status_code", 200)
        if status != 200:
            _raise_for_http_error(r, self.model)

        try:
            data = r.json()
        except Exception as exc:
            raise LLMInvalidResponseError("Invalid JSON in completion response",
                                          model=self.model, provider="openai") from exc

        if not isinstance(data, dict):
            raise LLMInvalidResponseError("Completion payload must be a JSON object",
                                          model=self.model, provider="openai")

        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            raise LLMInvalidResponseError("Completion response missing choices",
                                          model=self.model, provider="openai")

        first_choice = _as_dict(choices[0])
        message = _as_dict(first_choice.get("message"))
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict)
            )
        if not isinstance(content, str):
            content = ""

        finish_reason = first_choice.get("finish_reason")
        truncated = (finish_reason == "length")

        if not content.strip():
            raise LLMInvalidResponseError("Completion returned empty content",
                                          model=self.model, provider="openai",
                                          truncated=truncated)

        usage = _as_dict(data.get("usage"))
        input_details = _as_dict(usage.get("prompt_tokens_details"))
        output_details = _as_dict(usage.get("completion_tokens_details"))
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
        reasoning_tokens = int(output_details.get("reasoning_tokens") or 0)
        if reasoning_tokens == 0:
            reasoning_tokens = max(0, total_tokens - input_tokens - output_tokens)

        latency = (time.perf_counter() - start) * 1000
        logger.debug("LLM call: %s chars in %.1fms", len(content), latency)
        return LLMResponse(
            text=content,
            model=self.model,
            latency_ms=latency,
            ok=True,
            truncated=truncated,
            finish_reason=str(finish_reason) if finish_reason else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_tokens=int(input_details.get("cached_tokens") or 0),
            reasoning_tokens=reasoning_tokens,
        )
