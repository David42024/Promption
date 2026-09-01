"""Capa LLM: cliente OpenAI-compatible (Groq, OpenRouter, Gemini…) para entornos sin Ollama."""
from __future__ import annotations

import os
from typing import Any

import requests

from src.llm.ollama_client import LLMResponse
from src.utils.config import load_config
from src.utils.logger import logger

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


class OpenAICompatibleClient:
    """Cliente HTTP para APIs compatibles con OpenAI (POST /chat/completions).

    Configurable por variables de entorno:
      PIF_LLM_BASE_URL, PIF_LLM_MODEL, PIF_LLM_API_KEY
    """

    _DEFAULT_BASE = "https://api.groq.com/openai/v1"
    _DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(self, host: str | None = None, model: str | None = None,
                 timeout: int | None = None, api_key: str | None = None):
        openai = _CONF.get("openai", {})
        self.host = (host or os.environ.get("PIF_LLM_BASE_URL", "") or openai.get("base_url")
                     or self._DEFAULT_BASE).rstrip("/")
        self.model = (model or os.environ.get("PIF_LLM_MODEL", "") or openai.get("model")
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
        r = requests.get(f"{self.host}/models", headers=self._headers(), timeout=self.health_timeout)
        r.raise_for_status()
        return [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]

    def generate(self, prompt: str, system: str | None = None, temperature: float | None = None,
                 max_tokens: int | None = None) -> LLMResponse:
        import time
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else float(_CONF.get("temperature", 0.2)),
            "max_tokens": max_tokens if max_tokens is not None else int(_CONF.get("max_tokens", 200)),
            "stream": False,
        }
        start = time.perf_counter()
        r = requests.post(f"{self.host}/chat/completions", json=payload,
                          headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        message = choices[0].get("message") if choices else {}
        content = message.get("content") or ""
        latency = (time.perf_counter() - start) * 1000
        logger.debug("LLM call: %s chars in %.1fms", len(content), latency)
        return LLMResponse(text=content, model=self.model, latency_ms=latency)