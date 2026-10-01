"""Filter API client integration"""
import asyncio
import logging
import httpx
from typing import Optional, Dict, Any
from .api.models import FilterResponse


logger = logging.getLogger(__name__)


class FilterRateLimited(RuntimeError):
    """The remote filter rejected the request after bounded retries."""


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    try:
        return min(max(float(response.headers.get("Retry-After", "")), 0.0), 2.0)
    except ValueError:
        return 0.25 * (attempt + 1)


async def _post_with_rate_limit_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    for attempt in range(3):
        response = await client.post(url, **kwargs)
        if response.status_code != 429 or attempt == 2:
            return response
        await asyncio.sleep(_retry_delay(response, attempt))
    raise RuntimeError("Rate limit retry exhausted")


class FilterClient:
    """Client for Filter API integration"""
    
    def __init__(self, *, base_url: str, api_key: str, tenant_id: str | None = None,
                 timeout: float = 60.0, context: dict | None = None, response_model=FilterResponse):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.timeout = timeout
        self.context = dict(context or {})
        self.response_model = response_model

    @property
    def headers(self) -> Dict[str, str]:
        if not self.base_url:
            raise RuntimeError("FILTER_API_URL is not configured")
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
        use_ml: bool = True,
        messages: list[dict] | None = None
    ) -> FilterResponse:
        """Filter a prompt through the Filter API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await _post_with_rate_limit_retry(client,
                    f"{self.base_url}/api/v1/filter",
                    headers=self.headers,
                    json={
                        "text": text,
                        "use_ml": use_ml,
                        "messages": messages or [],
                        "user_id": user_id,
                        "roles": roles,
                        "context": {**self.context, "roles": roles}
                    }
                )
                
                if response.status_code == 401:
                    raise ValueError("Invalid Filter API key")
                if response.status_code == 429:
                    raise FilterRateLimited("Filter API rate limit exceeded")
                
                if response.status_code != 200:
                    raise RuntimeError(f"Filter API error {response.status_code}")
                
                data = response.json()
                self._validate_tenant(data)
                if messages:
                    conversation = (data.get("layers") or {}).get("conversation", {})
                    if conversation.get("message_count") != len(messages) or not isinstance(conversation.get("blocked"), bool):
                        raise RuntimeError("Filter API did not inspect the conversation")
                logger.debug("Filter API decision=%s", data.get("decision"))
                return self.response_model(**data)
                
        except httpx.TimeoutException:
            raise Exception("Filter API timeout")
        except FilterRateLimited:
            raise
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
                response = await _post_with_rate_limit_retry(client,
                    f"{self.base_url}/api/v1/output-guard",
                    headers=self.headers,
                    json={
                        "text": text,
                        "user_id": user_id,
                        "roles": roles,
                        "context": {**self.context, "roles": roles}
                    }
                )
                
                if response.status_code == 401:
                    raise ValueError("Invalid Filter API key")
                if response.status_code == 429:
                    raise FilterRateLimited("Output Guard rate limit exceeded")
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
