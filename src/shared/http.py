"""HTTP client helpers — proxy-aware httpx clients.

Used by both core (API polling) and trading (order execution).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from shared.config import PROXY_URL

logger = logging.getLogger(__name__)


def get_async_http_client(**kwargs) -> httpx.AsyncClient:
    """Create a proxy-aware async HTTP client."""
    client_kwargs = _build_client_kwargs(proxy_url=PROXY_URL, **kwargs)
    try:
        return httpx.AsyncClient(**client_kwargs)
    except ImportError as exc:
        if not _should_retry_without_proxy(exc, client_kwargs):
            raise
        fallback_kwargs = _fallback_client_kwargs(client_kwargs)
        logger.warning(
            "SOCKS proxy support is unavailable; retrying async HTTP client without proxy. "
            "Install `httpx[socks]` or unset `PROXY_URL` to silence this warning."
        )
        return httpx.AsyncClient(**fallback_kwargs)


def get_sync_http_client(**kwargs) -> httpx.Client:
    """Create a proxy-aware sync HTTP client."""
    client_kwargs = _build_client_kwargs(proxy_url=PROXY_URL, **kwargs)
    try:
        return httpx.Client(**client_kwargs)
    except ImportError as exc:
        if not _should_retry_without_proxy(exc, client_kwargs):
            raise
        fallback_kwargs = _fallback_client_kwargs(client_kwargs)
        logger.warning(
            "SOCKS proxy support is unavailable; retrying sync HTTP client without proxy. "
            "Install `httpx[socks]` or unset `PROXY_URL` to silence this warning."
        )
        return httpx.Client(**fallback_kwargs)


def _build_client_kwargs(*, proxy_url: str, **kwargs: Any) -> dict[str, Any]:
    client_kwargs = dict(kwargs)
    if proxy_url:
        client_kwargs.setdefault("proxy", proxy_url)
    client_kwargs.setdefault("timeout", 30.0)
    return client_kwargs


def _fallback_client_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    fallback_kwargs = dict(kwargs)
    fallback_kwargs.pop("proxy", None)
    fallback_kwargs.setdefault("trust_env", False)
    return fallback_kwargs


def _should_retry_without_proxy(exc: ImportError, kwargs: dict[str, Any]) -> bool:
    if "proxy" not in kwargs:
        return False
    message = str(exc).lower()
    return "socks" in message or "socksio" in message
