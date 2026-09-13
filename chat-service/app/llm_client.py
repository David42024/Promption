"""LLM client integration (OpenAI/Gemini/Groq/OpenRouter)"""
import httpx
from typing import Optional, List, Dict, Any
from .config import settings
from .models import LLMResponse


class LLMClient:
    """Client for LLM integration with provider fallback"""
    
    def __init__(self):
        self.openai_api_key = settings.openai_api_key
        self.gemini_api_key = settings.gemini_api_key
        self.groq_api_key = settings.groq_api_key
        self.openrouter_api_key = settings.openrouter_api_key
        self.default_model = settings.default_model
        self.timeout = 30.0
        
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
        
        for provider in provider_order:
            models.extend(models_by_provider.get(provider, []))

        for provider, provider_models in models_by_provider.items():
            if provider not in provider_order:
                models.extend(provider_models)

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
                "temperature": 0.18,
                "max_tokens": 600
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
        """Generate response from LLM with fallback"""
        import time
        
        if not self.models:
            raise Exception(
                "No LLM providers configured. Please set OPENAI_API_KEY, GEMINI_API_KEY, "
                "GROQ_API_KEY or OPENROUTER_API_KEY environment variables."
            )
        
        last_error = None
        
        for model_config in self.models:
            for attempt in range(3):  # 3 retries per model
                try:
                    headers = {"Content-Type": "application/json"}
                    
                    resolved_temperature = temperature or model_config["temperature"]
                    resolved_max_tokens = max_tokens or model_config["max_tokens"]
                    request_url = model_config["base_url"]

                    if model_config["api"] == "gemini":
                        request_url = f"{request_url}?key={model_config['api_key']}"
                        payload = self._build_gemini_payload(
                            messages,
                            resolved_temperature,
                            resolved_max_tokens
                        )
                    else:
                        headers["Authorization"] = f"Bearer {model_config['api_key']}"

                        if model_config["provider"] == "openrouter":
                            headers["HTTP-Referer"] = "https://promption.shop"
                            headers["X-Title"] = "Promption Shop Demo"
                        
                        payload = {
                            "model": model_config["model"],
                            "messages": messages,
                            "temperature": resolved_temperature,
                            "max_tokens": resolved_max_tokens,
                            "stream": False
                        }
                    
                    start_time = time.perf_counter()
                    
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.post(
                            request_url,
                            headers=headers,
                            json=payload
                        )
                    
                    latency = (time.perf_counter() - start_time) * 1000
                    
                    if response.status_code == 200:
                        data = response.json()
                        content = self._extract_text(model_config["provider"], data)
                        if not content:
                            last_error = f"{model_config['provider'].upper()} returned empty content"
                            break
                        return LLMResponse(
                            text=content,
                            model=model_config["label"],
                            latency_ms=latency,
                            ok=True
                        )
                    
                    # Handle rate limiting with retry
                    if response.status_code in [429, 500, 502, 503, 504] and attempt < 2:
                        import asyncio
                        await asyncio.sleep(1.2 ** attempt)  # Exponential backoff
                        continue
                    
                    last_error = f"{model_config['provider'].upper()} {response.status_code}: {response.text[:100]}"
                    break  # Try next model
                    
                except httpx.TimeoutException:
                    last_error = f"{model_config['provider'].upper()} timeout"
                    if attempt < 2:
                        import asyncio
                        await asyncio.sleep(1)
                        continue
                    break
                except Exception as e:
                    last_error = f"{model_config['provider'].upper()} {str(e)}"
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
