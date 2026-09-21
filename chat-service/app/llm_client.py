"""LLM client integration (Gemini/Groq/OpenRouter)."""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from .config import settings
from .models import LLMResponse


logger = logging.getLogger(__name__)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class LLMClient:
    """Client for LLM integration with provider fallback"""
    
    def __init__(self):
        self.openai_api_key = settings.openai_api_key
        self.gemini_api_key = settings.gemini_api_key
        self.groq_api_key = settings.groq_api_key
        self.openrouter_api_key = settings.openrouter_api_key
        self.default_model = settings.default_model
        self.provider_timeout = max(0.5, settings.llm_provider_timeout_seconds)
        self.total_timeout = max(0.5, settings.llm_total_timeout_seconds)
        self.max_attempts = max(1, settings.llm_max_attempts)
        self.retry_backoff = max(0.0, settings.llm_retry_backoff_seconds)
        
        # Model fallback chain
        self.models = self._get_available_models()
    
    def _get_available_models(self) -> List[Dict[str, Any]]:
        """Get available models with API keys"""
        models_by_provider = {
            "openai": self._get_openai_models(),
            "gemini": self._get_gemini_models(),
            "groq": self._get_groq_models(),
            "openrouter": self._get_openrouter_models(),
        }
        models: List[Dict[str, Any]] = []
        provider_order = [
            provider.strip().lower()
            for provider in settings.llm_provider_order.split(",")
            if provider.strip()
        ]

        ordered_providers = provider_order + [
            provider
            for provider in models_by_provider
            if provider not in provider_order
        ]
        for provider in ordered_providers:
            provider_models = models_by_provider.get(provider, [])
            if provider_models:
                models.append(provider_models[0])
        for provider in ordered_providers:
            models.extend(models_by_provider.get(provider, [])[1:])

        return models

    def _get_openai_models(self) -> List[Dict[str, Any]]:
        if not self.openai_api_key:
            return []
        return [
            {
                "id": "openai-primary",
                "label": f"OpenAI · {settings.openai_model}",
                "provider": "openai",
                "api": "openai_compatible",
                "model": settings.openai_model,
                "api_key": self.openai_api_key,
                "base_url": "https://api.openai.com/v1/chat/completions",
                "temperature": 0.2,
                "max_tokens": 600,
            }
        ]

    def _get_gemini_models(self) -> List[Dict[str, Any]]:
        if not self.gemini_api_key:
            return []

        return [
            {
                "id": "gemini-primary",
                "label": f"Gemini · {settings.gemini_model}",
                "provider": "gemini",
                "api": "gemini",
                "model": settings.gemini_model,
                "api_key": self.gemini_api_key,
                "base_url": f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
                "temperature": 0.18,
                "max_tokens": 600
            }
        ]

    def _get_groq_models(self) -> List[Dict[str, Any]]:
        if self.groq_api_key:
            return [
                {
                    "id": "groq-fast",
                    "label": "Groq · Llama 3.1 70B",
                    "provider": "groq",
                    "api": "openai_compatible",
                    "model": "llama-3.1-70b-versatile",
                    "api_key": self.groq_api_key,
                    "base_url": "https://api.groq.com/openai/v1/chat/completions",
                    "temperature": 0.18,
                    "max_tokens": 600
                },
                {
                    "id": "groq-small",
                    "label": "Groq · Llama 3.1 8B",
                    "provider": "groq",
                    "api": "openai_compatible",
                    "model": "llama-3.1-8b-instant",
                    "api_key": self.groq_api_key,
                    "base_url": "https://api.groq.com/openai/v1/chat/completions",
                    "temperature": 0.22,
                    "max_tokens": 600
                }
            ]

        return []

    def _get_openrouter_models(self) -> List[Dict[str, Any]]:
        if self.openrouter_api_key:
            return [
                {
                    "id": "or-qwen",
                    "label": "OpenRouter · Qwen 2.5 72B",
                    "provider": "openrouter",
                    "api": "openai_compatible",
                    "model": "qwen/qwen-2.5-72b-instruct",
                    "api_key": self.openrouter_api_key,
                    "base_url": "https://openrouter.ai/api/v1/chat/completions",
                    "temperature": 0.22,
                    "max_tokens": 600
                }
            ]

        return []
    
    async def check_health(self) -> bool:
        """Check if any LLM provider is available"""
        return len(self.models) > 0

    def _build_gemini_payload(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> Dict[str, Any]:
        system_parts = []
        contents = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                system_parts.append({"text": content})
                continue

            gemini_role = "model" if role == "assistant" else "user"
            contents.append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}

        return payload

    def _extract_text(self, provider: str, data: Dict[str, Any]) -> str:
        if provider == "gemini":
            candidates = data.get("candidates", [])
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(part.get("text", "") for part in parts).strip()

        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    
    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Generate a response using an ordered fallback within one time budget."""
        if not self.models:
            raise Exception(
                "No LLM providers configured. Please set OPENAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY "
                "or OPENROUTER_API_KEY environment variables."
            )

        chain_started = time.perf_counter()
        last_error = None
        async with httpx.AsyncClient() as client:
            for model_config in self.models:
                for attempt in range(self.max_attempts):
                    elapsed = time.perf_counter() - chain_started
                    remaining = self.total_timeout - elapsed
                    if remaining <= 0:
                        last_error = "total timeout exhausted"
                        break

                    headers = {"Content-Type": "application/json"}
                    resolved_temperature = (
                        temperature
                        if temperature is not None
                        else model_config["temperature"]
                    )
                    resolved_max_tokens = (
                        max_tokens
                        if max_tokens is not None
                        else model_config["max_tokens"]
                    )
                    request_url = model_config["base_url"]

                    if model_config["api"] == "gemini":
                        request_url = f"{request_url}?key={model_config['api_key']}"
                        payload = self._build_gemini_payload(
                            messages,
                            resolved_temperature,
                            resolved_max_tokens,
                        )
                    else:
                        headers["Authorization"] = f"Bearer {model_config['api_key']}"
                        if model_config["provider"] == "openrouter":
                            headers["HTTP-Referer"] = "https://promption.shop"
                            headers["X-Title"] = "Promption Shop Demo"

                        is_gpt5 = (
                            model_config["provider"] == "openai"
                            and model_config["model"].lower().startswith("gpt-5")
                        )
                        if is_gpt5:
                            payload = {
                                "model": model_config["model"],
                                "messages": messages,
                                "max_completion_tokens": resolved_max_tokens,
                                "reasoning_effort": "minimal",
                                "stream": False,
                            }
                        else:
                            payload = {
                                "model": model_config["model"],
                                "messages": messages,
                                "temperature": resolved_temperature,
                                "max_tokens": resolved_max_tokens,
                                "stream": False,
                            }

                    request_timeout = min(self.provider_timeout, remaining)
                    try:
                        response = await client.post(
                            request_url,
                            headers=headers,
                            json=payload,
                            timeout=request_timeout,
                        )
                    except httpx.TimeoutException:
                        last_error = f"{model_config['provider'].upper()} timeout"
                        logger.warning(
                            "LLM timeout provider=%s model=%s attempt=%d timeout=%.1fs",
                            model_config["provider"],
                            model_config["model"],
                            attempt + 1,
                            request_timeout,
                        )
                    except Exception as exc:
                        last_error = (
                            f"{model_config['provider'].upper()} "
                            f"{exc.__class__.__name__}"
                        )
                        logger.warning(
                            "LLM client error provider=%s model=%s attempt=%d error=%s",
                            model_config["provider"],
                            model_config["model"],
                            attempt + 1,
                            exc.__class__.__name__,
                        )
                        break
                    else:
                        if response.is_success:
                            try:
                                data = response.json()
                                content = self._extract_text(
                                    model_config["provider"], data
                                )
                            except (IndexError, KeyError, TypeError, ValueError):
                                content = ""
                                logger.warning(
                                    "LLM returned an invalid payload provider=%s model=%s",
                                    model_config["provider"],
                                    model_config["model"],
                                )
                            if content:
                                latency = (
                                    time.perf_counter() - chain_started
                                ) * 1000
                                return LLMResponse(
                                    text=content,
                                    model=model_config["label"],
                                    latency_ms=latency,
                                    ok=True,
                                )
                            last_error = f"{model_config['provider'].upper()} invalid or empty content"
                        else:
                            last_error = (
                                f"{model_config['provider'].upper()} "
                                f"HTTP {response.status_code}"
                            )
                            logger.warning(
                                "LLM rejected provider=%s model=%s attempt=%d status=%d",
                                model_config["provider"],
                                model_config["model"],
                                attempt + 1,
                                response.status_code,
                            )
                            if response.status_code not in _RETRYABLE_STATUS_CODES:
                                break

                    if attempt + 1 < self.max_attempts:
                        remaining = self.total_timeout - (
                            time.perf_counter() - chain_started
                        )
                        delay = min(
                            self.retry_backoff * (2 ** attempt),
                            max(0.0, remaining),
                        )
                        if delay > 0:
                            await asyncio.sleep(delay)

                if time.perf_counter() - chain_started >= self.total_timeout:
                    break

        raise Exception(f"All LLM providers failed: {last_error}")


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get singleton LLMClient instance"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
