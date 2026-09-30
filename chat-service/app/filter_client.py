"""Application configuration for the reusable Promption HTTP client."""
from promption.client import FilterClient as BaseFilterClient
from .config import settings
from .models import FilterResponse


class FilterClient(BaseFilterClient):
    def __init__(self):
        super().__init__(base_url=settings.filter_api_url,
                         api_key=settings.promption_api_key or settings.filter_api_key,
                         tenant_id=settings.tenant_id,
                         context={"channel": "demo-chat", "data_tiers": ["publico", "interno", "confidencial"]},
                         response_model=FilterResponse)


_filter_client: FilterClient | None = None


def get_filter_client() -> FilterClient:
    global _filter_client
    if _filter_client is None:
        _filter_client = FilterClient()
    return _filter_client
