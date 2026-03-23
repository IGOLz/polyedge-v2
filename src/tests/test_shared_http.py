from __future__ import annotations

import unittest
from unittest.mock import patch

from shared.http import get_async_http_client, get_sync_http_client


class SharedHttpTests(unittest.TestCase):
    def test_async_http_client_falls_back_without_proxy_when_socks_support_missing(self):
        created_kwargs: list[dict] = []
        fallback_client = object()
        clients = [ImportError("Using SOCKS proxy, but the 'socksio' package is not installed."), fallback_client]

        def fake_async_client(**kwargs):
            created_kwargs.append(kwargs)
            result = clients.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("shared.http.PROXY_URL", "socks5://proxy.example:1080"), patch(
            "shared.http.httpx.AsyncClient",
            side_effect=fake_async_client,
        ):
            client = get_async_http_client(timeout=10.0)

        self.assertIs(client, fallback_client)
        self.assertEqual(created_kwargs[0]["proxy"], "socks5://proxy.example:1080")
        self.assertEqual(created_kwargs[1]["timeout"], 10.0)
        self.assertFalse(created_kwargs[1]["trust_env"])
        self.assertNotIn("proxy", created_kwargs[1])

    def test_sync_http_client_falls_back_without_proxy_when_socks_support_missing(self):
        created_kwargs: list[dict] = []
        fallback_client = object()
        clients = [ImportError("Using SOCKS proxy, but the 'socksio' package is not installed."), fallback_client]

        def fake_sync_client(**kwargs):
            created_kwargs.append(kwargs)
            result = clients.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("shared.http.PROXY_URL", "socks5://proxy.example:1080"), patch(
            "shared.http.httpx.Client",
            side_effect=fake_sync_client,
        ):
            client = get_sync_http_client(timeout=12.0)

        self.assertIs(client, fallback_client)
        self.assertEqual(created_kwargs[0]["proxy"], "socks5://proxy.example:1080")
        self.assertEqual(created_kwargs[1]["timeout"], 12.0)
        self.assertFalse(created_kwargs[1]["trust_env"])
        self.assertNotIn("proxy", created_kwargs[1])
