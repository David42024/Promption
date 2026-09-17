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
        self.api_key = settings.promption_api_key or settings.filter_api_key
        self.tenant_id = settings.tenant_id
        self.timeout = 60.0  # Timeout alto para manejar cold starts de Render

    @property
    def headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RuntimeError("PROMPTION_API_KEY is not configured")
        return {
            "Content-Type": "application/json",
            "X-Promption-API-Key": self.api_key,
        }

    def _validate_tenant(self, data: Dict[str, Any]) -> None:
        resolved_tenant = data.get("tenant_id")
        if self.tenant_id and resolved_tenant != self.tenant_id:
            raise RuntimeError(
                f"Promption API key belongs to tenant '{resolved_tenant}', "
                f"not expected tenant '{self.tenant_id}'"
            )
    
    async def check_health(self) -> bool:
        """Check that the Filter API is reachable and this business key is valid."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                tenant = await client.get(
                    f"{self.base_url}/api/v1/tenant",
                    headers=self.headers,
                )
                if tenant.status_code != 200:
                    return False
                data = tenant.json()
                self._validate_tenant(data)
                return True
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
                    headers=self.headers,
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
                self._validate_tenant(data)
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
                    headers=self.headers,
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
                data = response.json()
                self._validate_tenant(data)
                return data

        except httpx.TimeoutException as exc:
            raise Exception("Output Guard timeout") from exc
        except Exception as exc:
            logger.warning("Output Guard client error: %s", exc)
            raise

    async def audit_event(
        self,
        *,
        event_type: str,
        user_id: str,
        roles: list[str],
        details: Dict[str, Any],
        level: str = "INFO",
    ) -> None:
        """Emit a sanitized chat lifecycle event without affecting the user response."""
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 2.0)) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/audit/events",
                    headers=self.headers,
                    json={
                        "category": "chat",
                        "event_type": event_type,
                        "level": level,
                        "message": f"Chat request completed: {details.get('decision', 'UNKNOWN')}",
                        "user_id": user_id,
                        "roles": roles,
                        "details": details,
                    },
                )
                if not response.is_success:
                    logger.warning("Audit API rejected event status=%s", response.status_code)
        except Exception as exc:
            logger.warning("Audit event unavailable: %s", exc.__class__.__name__)


# Singleton instance
_filter_client: Optional[FilterClient] = None


def get_filter_client() -> FilterClient:
    """Get singleton FilterClient instance"""
    global _filter_client
    if _filter_client is None:
        _filter_client = FilterClient()
    return _filter_client
