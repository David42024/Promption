"""Filter API client integration"""
import logging
import httpx
from typing import Optional, Dict, Any
from .config import settings
from .models import FilterResponse


logger = logging.getLogger(__name__)


class FilterClient:
    """Client for Filter API integration"""
    
    def __init__(self):
        self.base_url = settings.filter_api_url.rstrip("/")
        self.api_key = settings.filter_api_key
        self.tenant_id = settings.tenant_id
        self.timeout = 60.0  # Timeout alto para manejar cold starts de Render
    
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
                            "data_tiers": ["publico", "interno", "confidencial"],
                            "roles": roles
                        }
                    }
                )
                
                if response.status_code == 401:
                    raise ValueError("Invalid Filter API key")
                
                if response.status_code != 200:
                    error_text = response.text
                    raise Exception(f"Filter API error {response.status_code}: {error_text}")
                
                data = response.json()
                logger.debug("Filter API decision=%s", data.get("decision"))
                return FilterResponse(**data)
                
        except httpx.TimeoutException:
            raise Exception("Filter API timeout")
        except Exception as e:
            logger.warning("Filter client error: %s", e)
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
                            "data_tiers": ["publico", "interno", "confidencial"],
                            "roles": roles
                        }
                    }
                )
                
                if response.status_code == 401:
                    raise ValueError("Invalid Filter API key")
                if not response.is_success:
                    raise Exception(f"Output Guard error {response.status_code}")
                return response.json()

        except httpx.TimeoutException as exc:
            raise Exception("Output Guard timeout") from exc
        except Exception as exc:
            logger.warning("Output Guard client error: %s", exc)
            raise


# Singleton instance
_filter_client: Optional[FilterClient] = None


def get_filter_client() -> FilterClient:
    """Get singleton FilterClient instance"""
    global _filter_client
    if _filter_client is None:
        _filter_client = FilterClient()
    return _filter_client
