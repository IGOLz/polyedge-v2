"""HTTP client helpers — proxy-aware httpx clients.

Used by both core (API polling) and trading (order execution).
"""

import httpx

from shared.config import PROXY_URL


def get_async_http_client(**kwargs) -> httpx.AsyncClient:
    """Create a proxy-aware async HTTP client."""
    if PROXY_URL:
        kwargs.setdefault("proxy", PROXY_URL)
    kwargs.setdefault("timeout", 30.0)
    return httpx.AsyncClient(**kwargs)


def get_sync_http_client(**kwargs) -> httpx.Client:
    """Create a proxy-aware sync HTTP client."""
    if PROXY_URL:
        kwargs.setdefault("proxy", PROXY_URL)
    kwargs.setdefault("timeout", 30.0)
    return httpx.Client(**kwargs)
