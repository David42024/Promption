"""Filter API client integration"""
import asyncio
import logging
import random
from typing import Optional, Dict, Any
import httpx
from .api.models import FilterResponse
from .guard import Identity
from promption.llm.exceptions import parse_retry_after


logger = logging.getLogger(__name__)


class FilterRateLimited(RuntimeError):
    """The remote filter rejected the request after bounded retries."""


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    parsed = parse_retry_after(response.headers.get("Retry-After"))
    if parsed is not None:
        return parsed
    base = 0.25 * (2 ** attempt)
    return base + random.uniform(0.02, 0.08)


async def _post_with_rate_limit_retry(
    client: httpx.AsyncClient,
    url: str,
    max_budget: Optional[float] = None,
    **kwargs
) -> httpx.Response:
    start = asyncio.get_event_loop().time()
    for attempt in range(3):
        if max_budget is not None and (asyncio.get_event_loop().time() - start) >= max_budget:
            raise FilterRateLimited("Rate limit retry budget exhausted")
        response = await client.post(url, **kwargs)
        if response.status_code != 429 or attempt == 2:
            return response
        delay = _retry_delay(response, attempt)
        if max_budget is not None and ((asyncio.get_event_loop().time() - start) + delay) > max_budget:
            # Do not shorten long Retry-After; fail immediately if exceeding budget
            raise FilterRateLimited(f"Filter API rate limit Retry-After ({delay:.1f}s) exceeds available budget")
        await asyncio.sleep(delay)
    raise FilterRateLimited("Rate limit retry exhausted")


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
    
    async def check_health(self, timeout: float | None = None) -> bool:
        """Check that the Filter API is reachable and this business key is valid."""
        req_timeout = timeout if timeout is not None else self.timeout
        try:
            async with httpx.AsyncClient(timeout=req_timeout) as client:
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
        identity: 'Identity',
        use_ml: bool = True,
        messages: list[dict] | None = None,
        timeout: float | None = None,
    ) -> FilterResponse:
        """Filter a prompt through the Filter API"""
        req_timeout = timeout if timeout is not None else self.timeout
        try:
            async with httpx.AsyncClient(timeout=req_timeout) as client:
                response = await _post_with_rate_limit_retry(
                    client,
                    f"{self.base_url}/api/v1/filter",
                    max_budget=req_timeout,
                    headers=self.headers,
                    json={
                        "text": text,
                        "use_ml": use_ml,
                        "messages": messages or [],
                        "user_id": identity.user_id,
                        "roles": list(identity.roles),
                        "context": {**self.context, "roles": list(identity.roles)}
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
        identity: Identity,
        timeout: float | None = None,
    ) -> Dict[str, Any]:
        """Check output through Output Guard"""
        req_timeout = timeout if timeout is not None else self.timeout
        try:
            async with httpx.AsyncClient(timeout=req_timeout) as client:
                response = await _post_with_rate_limit_retry(
                    client,
                    f"{self.base_url}/api/v1/output-guard",
                    max_budget=req_timeout,
                    headers=self.headers,
                    json={
                        "text": text,
                        "user_id": identity.user_id,
                        "roles": list(identity.roles),
                        "context": {**self.context, "roles": list(identity.roles)}
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
        identity: Identity,
        details: Dict[str, Any],
        level: str = "INFO",
        timeout: float | None = None,
    ) -> None:
        """Emit a sanitized chat lifecycle event without affecting the user response."""
        req_timeout = min(timeout if timeout is not None else self.timeout, 2.0)
        try:
            async with httpx.AsyncClient(timeout=req_timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/audit/events",
                    headers=self.headers,
                    json={
                        "category": "chat",
                        "event_type": event_type,
                        "level": level,
                        "message": f"Chat request completed: {details.get('decision', 'UNKNOWN')}",
                        "user_id": identity.user_id,
                        "roles": list(identity.roles),
                        "details": details,
                    },
                )
                if not response.is_success:
                    logger.warning("Audit API rejected event status=%s", response.status_code)
        except Exception as exc:
            logger.warning("Audit event unavailable: %s", exc.__class__.__name__)
