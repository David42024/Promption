"""Filter API client integration"""
import httpx
import time
from typing import Optional, Dict, Any
from .config import settings
from .models import FilterResponse


class FilterClient:
    """Client for Filter API integration"""
    
    def __init__(self):
        self.base_url = settings.filter_api_url.rstrip("/")
        self.api_key = settings.filter_api_key
        self.tenant_id = settings.tenant_id
        self.timeout = 60.0  # Aumentado a 60s para manejar cold starts de Render
        self._failure_count = 0
        self._last_failure_time = 0
        self._circuit_breaker_threshold = 3  # 3 fallos seguidos desactivan el Filter API temporalmente
        self._circuit_breaker_cooldown = 300  # 5 minutos cooldown
    
    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open (Filter API temporarily disabled)"""
        if self._failure_count >= self._circuit_breaker_threshold:
            # Verificar si ha pasado el cooldown
            if time.time() - self._last_failure_time < self._circuit_breaker_cooldown:
                return True
            else:
                # Reset después del cooldown
                self._failure_count = 0
        return False
    
    def _record_failure(self):
        """Record a failure and update circuit breaker state"""
        self._failure_count += 1
        self._last_failure_time = time.time()
    
    def _record_success(self):
        """Record a success and reset circuit breaker"""
        self._failure_count = 0
    
    async def check_health(self) -> bool:
        """Check if Filter API is healthy"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/v1/health")
                return response.status_code == 200
        except Exception:
            return False
    
    async def filter_prompt(
        self, 
        text: str, 
        user_id: str, 
        roles: list[str],
        use_ml: bool = True
    ) -> FilterResponse:
        """Filter a prompt through the Filter API"""
        # Check circuit breaker
        if self._is_circuit_open():
            raise Exception("Filter API circuit breaker open (too many failures)")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/filter",
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": self.api_key
                    },
                    json={
                        "text": text,
                        "use_ml": use_ml,
                        "user_id": user_id,
                        "roles": roles,
                        "context": {
                            "channel": "demo-chat",
                            "data_tiers": ["publico", "interno", "confidencial"]
                        }
                    }
                )
                
                if response.status_code == 401:
                    raise ValueError("Invalid Filter API key")
                
                if not response.ok:
                    error_text = response.text
                    raise Exception(f"Filter API error {response.status_code}: {error_text}")
                
                data = response.json()
                self._record_success()  # Reset circuit breaker on success
                return FilterResponse(**data)
                
        except httpx.TimeoutException:
            self._record_failure()
            raise Exception("Filter API timeout")
        except Exception as e:
            self._record_failure()
            raise Exception(f"Filter API error: {str(e)}")
    
    async def output_guard(
        self,
        text: str,
        user_id: str,
        roles: list[str]
    ) -> Dict[str, Any]:
        """Check output through Output Guard"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/output-guard",
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": self.api_key
                    },
                    json={
                        "text": text,
                        "user_id": user_id,
                        "roles": roles,
                        "context": {
                            "channel": "demo-chat",
                            "data_tiers": ["publico", "interno", "confidencial"]
                        }
                    }
                )
                
                if response.ok:
                    return response.json()
                else:
                    return {"action": "SKIPPED"}
                    
        except Exception:
            return {"action": "SKIPPED"}


# Singleton instance
_filter_client: Optional[FilterClient] = None


def get_filter_client() -> FilterClient:
    """Get singleton FilterClient instance"""
    global _filter_client
    if _filter_client is None:
        _filter_client = FilterClient()
    return _filter_client