"""Selección del cliente LLM: Ollama local o API compatible con OpenAI."""
import os

from src.llm.ollama_client import LLMResponse, OllamaClient
from src.llm.openai_client import OpenAICompatibleClient, resolve_api_key
from src.utils.config import load_config

__all__ = ["LLMResponse", "OllamaClient", "OpenAICompatibleClient", "get_llm_client"]


def get_llm_client(host: str | None = None, model: str | None = None,
                   timeout: int | None = None) -> object:
    """Devuelve el cliente según PIF_LLM_PROVIDER (ollama|openai|auto).

    Con `auto` (por defecto) usa la API OpenAI-compatible si hay PIF_LLM_API_KEY
    configurada y Ollama local en caso contrario.
    """
    conf = load_config().get("llm", {})
    provider = (os.environ.get("PIF_LLM_PROVIDER") or conf.get("provider", "auto")).strip().lower()
    if provider == "ollama":
        return OllamaClient(host=host, model=model, timeout=timeout)
    if provider == "openai":
        return OpenAICompatibleClient(host=host, model=model, timeout=timeout)
    if resolve_api_key():
        return OpenAICompatibleClient(host=host, model=model, timeout=timeout)
    return OllamaClient(host=host, model=model, timeout=timeout)