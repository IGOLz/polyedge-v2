"""Async HTTP fetcher for Polymarket wallet activity."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote_plus

import httpx

from analysis.wallet_forensics.utils import row_hash
from wallet_tracker.config import (
    DATA_API_BASE,
    GAMMA_API_BASE,
    WALLET_TRACKER_PAGE_LIMIT,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 6
MAX_OFFSET = 3000
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> Any:
    for attempt in range(MAX_RETRIES):
        response = await client.request(method, url, **kwargs)
        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
            delay = _retry_delay(response, attempt)
            logger.warning(
                "Retrying %s %s after HTTP %s (sleep %.1fs, attempt %s)",
                method, url, response.status_code, delay, attempt + 1,
            )
            await asyncio.sleep(delay)
            continue
        response.raise_for_status()
        return response.json()
    response.raise_for_status()
    return response.json()


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return min(30.0, float(2 ** attempt))


async def resolve_wallet(client: httpx.AsyncClient, profile_name: str) -> dict[str, Any]:
    encoded = quote_plus(profile_name)
    payload = await _request_json(
        client,
        "GET",
        f"{GAMMA_API_BASE}/public-search?q={encoded}&search_profiles=true&limit_per_type=10",
    )
    candidates = payload.get("profiles") or []
    if not candidates:
        raise RuntimeError(f"No profile match found for {profile_name!r}")

    lowered = profile_name.strip().lower()
    exact = next(
        (item for item in candidates if str(item.get("name", "")).strip().lower() == lowered),
        None,
    )
    return exact or candidates[0]


async def fetch_activity(
    client: httpx.AsyncClient,
    proxy_wallet: str,
    *,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    offset = 0
    limit = WALLET_TRACKER_PAGE_LIMIT

    while True:
        params: dict[str, Any] = {
            "user": proxy_wallet,
            "limit": limit,
            "offset": offset,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        }
        if start_ts is not None:
            params["start"] = start_ts
        if end_ts is not None:
            params["end"] = end_ts

        try:
            page = await _request_json(client, "GET", f"{DATA_API_BASE}/activity", params=params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                logger.warning(
                    "API returned 400 at offset %d; stopping pagination with %d rows collected",
                    offset, len(seen),
                )
                break
            raise
        if not page:
            break

        for row in page:
            digest = row_hash(row)
            row["record_hash"] = digest
            seen[digest] = row

        if len(page) < limit:
            break
        offset += limit
        if offset >= MAX_OFFSET:
            logger.warning("Reached max offset %d; stopping pagination with %d rows", MAX_OFFSET, len(seen))
            break

    rows = list(seen.values())
    rows.sort(key=lambda item: int(item.get("timestamp") or 0))
    return rows
