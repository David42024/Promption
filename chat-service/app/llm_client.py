"""LLM client integration (Groq/OpenRouter)"""
import httpx
from typing import Optional, List, Dict, Any
from .config import settings
from .models import LLMResponse


class LLMClient:
    """Client for LLM integration (Groq/OpenRouter)"""
    
    def __init__(self):
        self.groq_api_key = settings.groq_api_key
        self.openrouter_api_key = settings.openrouter_api_key
        self.default_model = settings.default_model
        self.timeout = 30.0
        
        # Model fallback chain
        self.models = self._get_available_models()
    
    def _get_available_models(self) -> List[Dict[str, Any]]:
        """Get available models with API keys"""
        models = []
        
        if self.groq_api_key:
            models.extend([
                {
                    "id": "groq-fast",
                    "label": "Groq · Llama 3.1 70B",
                    "provider": "groq",
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
                    "model": "llama-3.1-8b-instant",
                    "api_key": self.groq_api_key,
                    "base_url": "https://api.groq.com/openai/v1/chat/completions",
                    "temperature": 0.22,
                    "max_tokens": 600
                }
            ])
        
        if self.openrouter_api_key:
            models.extend([
                {
                    "id": "or-qwen",
                    "label": "OpenRouter · Qwen 2.5 72B",
                    "provider": "openrouter",
                    "model": "qwen/qwen-2.5-72b-instruct",
                    "api_key": self.openrouter_api_key,
                    "base_url": "https://openrouter.ai/api/v1/chat/completions",
                    "temperature": 0.22,
                    "max_tokens": 600
                }
            ])
        
        return models
    
    async def check_health(self) -> bool:
        """Check if any LLM provider is available"""
        return len(self.models) > 0
    
    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Generate response from LLM with fallback"""
        import time
        
        if not self.models:
            raise Exception("No LLM providers configured")
        
        last_error = None
        
        for model_config in self.models:
            for attempt in range(3):  # 3 retries per model
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {model_config['api_key']}"
                    }
                    
                    if model_config["provider"] == "openrouter":
                        headers["HTTP-Referer"] = "https://promption.shop"
                        headers["X-Title"] = "Promption Shop Demo"
                    
                    payload = {
                        "model": model_config["model"],
                        "messages": messages,
                        "temperature": temperature or model_config["temperature"],
                        "max_tokens": max_tokens or model_config["max_tokens"],
                        "stream": False
                    }
                    
                    start_time = time.perf_counter()
                    
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.post(
                            model_config["base_url"],
                            headers=headers,
                            json=payload
                        )
                    
                    latency = (time.perf_counter() - start_time) * 1000
                    
                    if response.ok:
                        data = response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
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
                    
                    last_error = f"{model_config['provider'].upper()} {response.status_code}"
                    break  # Try next model
                    
                except httpx.TimeoutException:
                    last_error = f"{model_config['provider'].upper()} timeout"
                    if attempt < 2:
                        import asyncio
                        await asyncio.sleep(1)
                        continue
                    break
                except Exception as e:
                    last_error = str(e)
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