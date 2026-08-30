"""Thin client for Ollama's HTTP API (works with or without the ``ollama`` SDK)."""
from __future__ import annotations

from dataclasses import dataclass

import requests

from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config().get("llm", {})


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: float
    ok: bool = True


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
            return {"connected": False, "host": self.host, "models": [], "default_model": self.model,
                    "error": str(exc)}

    def list_models(self) -> list[str]:
        r = requests.get(f"{self.host}/api/tags", timeout=self.health_timeout)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

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
        r = requests.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        latency = (time.perf_counter() - start) * 1000
        logger.debug("LLM call: %s chars in %.1fms", len(data.get("response", "")), latency)
        return LLMResponse(text=data.get("response", ""), model=self.model, latency_ms=latency)


if __name__ == "__main__":
    c = OllamaClient()
    print("health:", c.health())
    if c.health()["connected"]:
        resp = c.generate("Di hola en español")
        print("resp:", resp.text[:200])