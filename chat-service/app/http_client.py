"""Managed HTTP client lifecycle and connection pooling for Chat Service."""
from __future__ import annotations

import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_shared_client: Optional[httpx.AsyncClient] = None


def create_shared_http_client(
    transport: Optional[httpx.AsyncBaseTransport] = None,
    max_connections: int = 100,
    max_keepalive_connections: int = 20,
    keepalive_expiry: float = 30.0,
    connect_timeout: float = 5.0,
    read_timeout: float = 60.0,
    write_timeout: float = 10.0,
    pool_timeout: float = 5.0,
) -> httpx.AsyncClient:
    """Creates a configured AsyncClient with pooled persistent connections."""
    limits = httpx.Limits(
        max_connections=max_connections,
        max_keepalive_connections=max_keepalive_connections,
        keepalive_expiry=keepalive_expiry,
    )
    timeout = httpx.Timeout(
        timeout=read_timeout,
        connect=connect_timeout,
        read=read_timeout,
        write=write_timeout,
        pool=pool_timeout,
    )
    try:
        return httpx.AsyncClient(
            transport=transport,
            limits=limits,
            timeout=timeout,
            follow_redirects=False,
        )
    except TypeError:
        return httpx.AsyncClient()


def get_shared_http_client() -> httpx.AsyncClient:
    """Returns the shared application AsyncClient, creating one if not initialized."""
    global _shared_client
    if _shared_client is None or getattr(_shared_client, 'is_closed', False):
        _shared_client = create_shared_http_client()
    return _shared_client


def set_shared_http_client(client: Optional[httpx.AsyncClient]) -> None:
    """Sets or overrides the shared AsyncClient (for testing and transport injection)."""
    global _shared_client
    _shared_client = client


async def close_shared_http_client() -> None:
    """Closes the shared AsyncClient cleanly on application shutdown."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        try:
            await _shared_client.aclose()
        except Exception as exc:
            logger.warning("Error closing shared HTTP client: %s", exc)
    _shared_client = None
