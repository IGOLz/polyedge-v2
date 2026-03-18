"""Polymarket API calls — market discovery and resolution polling.

Used by core (discovery loop) and can be reused by trading for market info.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from shared.config import POLYMARKET_API
from shared.models import MarketState

logger = logging.getLogger(__name__)

CLOB_REST_BASE = POLYMARKET_API["clob_rest_base"]
GAMMA_API_BASE = POLYMARKET_API["gamma_api_base"]


def _short(mid: str) -> str:
    return f"{mid[:6]}...{mid[-3:]}" if len(mid) > 9 else mid


async def enrich_with_clob(
    client: httpx.AsyncClient,
    market_id: str,
    started_at: datetime,
    ended_at: datetime,
) -> Optional[MarketState]:
    """
    Call the CLOB API to get token IDs for a market.
    Confirms Up/Down assignment via tokens[*].outcome field.
    Falls back to positional (index 0 = Up) if outcomes are unlabeled.
    """
    try:
        resp = await client.get(
            f"{CLOB_REST_BASE}/markets/{market_id}", timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("CLOB enrich failed — %s: %s", _short(market_id), exc)
        return None

    tokens = data.get("tokens", [])
    if len(tokens) < 2:
        return None

    up_token_id: Optional[str] = None
    down_token_id: Optional[str] = None

    for token in tokens:
        outcome = (token.get("outcome") or "").upper()
        tid = token.get("token_id")
        if outcome == "UP":
            up_token_id = tid
        elif outcome == "DOWN":
            down_token_id = tid

    if not up_token_id or not down_token_id:
        up_token_id = tokens[0].get("token_id")
        down_token_id = tokens[1].get("token_id")

    if not up_token_id or not down_token_id:
        return None

    return MarketState(
        market_id=market_id,
        up_token_id=up_token_id,
        down_token_id=down_token_id,
        started_at=started_at,
        ended_at=ended_at,
    )


async def fetch_open_btc_5min_markets(client: httpx.AsyncClient) -> list[MarketState]:
    """
    Fetch active BTC 5-minute markets from the Gamma events API.

    Strategy:
      1. Query /events with tag_slug=bitcoin, ordered by 24hr volume.
      2. Filter to markets whose slug indicates BTC up-or-down 5M and
         whose trading window is strictly live right now.
      3. Enrich each match via the CLOB API to get authoritative token IDs.
    """
    now = datetime.now(timezone.utc)

    try:
        resp = await client.get(
            f"{GAMMA_API_BASE}/events",
            params={
                "active": "true",
                "archived": "false",
                "tag_slug": "bitcoin",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
                "limit": "100",
            },
            timeout=15,
        )
        resp.raise_for_status()
        events = resp.json()
    except Exception as exc:
        logger.error("Gamma API error: %s", exc)
        return []

    if isinstance(events, dict):
        events = events.get("data", [])

    results: list[MarketState] = []
    seen_market_ids: set[str] = set()

    for event in events:
        markets = event.get("markets") or []
        series_list = event.get("series") or []
        series_slugs = [(s.get("slug") or "").lower() for s in series_list]

        for market in markets:
            slug = (market.get("slug") or "").lower()
            question = (market.get("question") or "").lower()

            if not ("btc" in slug or "bitcoin" in slug or
                    "btc" in question or "bitcoin" in question):
                continue

            if not any(
                kw in slug or kw in question
                for kw in ("up-or-down", "updown", "up or down")
            ):
                continue

            if not ("updown-5m" in slug or any(s.endswith("-5m") for s in series_slugs)):
                continue

            market_id = market.get("conditionId") or market.get("condition_id")
            if not market_id:
                continue

            if not market.get("active", False) or market.get("closed", True):
                continue

            end_str = market.get("endDate") or market.get("end_date")
            if not end_str:
                continue
            try:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            window_start = end_dt - timedelta(minutes=5)

            if not (window_start <= now < end_dt):
                continue

            if market_id in seen_market_ids:
                continue
            seen_market_ids.add(market_id)

            state = await enrich_with_clob(client, market_id, window_start, end_dt)
            if state:
                results.append(state)

    if len(results) > 1:
        results.sort(key=lambda s: s.ended_at)
        results = results[:1]

    return results


async def fetch_market_resolution(
    client: httpx.AsyncClient, market_id: str
) -> Optional[dict]:
    """
    Fetch resolution data for a single market.
    Returns dict with keys: resolved, winner, final_up_price, total_volume
    or None if not yet resolved.
    """
    try:
        resp = await client.get(
            f"{CLOB_REST_BASE}/markets/{market_id}", timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("Resolution fetch failed — %s: %s", _short(market_id), exc)
        return None

    if not data.get("resolved", False):
        return None

    winner = data.get("winner") or data.get("outcome")
    if isinstance(winner, str):
        winner = winner.upper()
        if winner not in ("UP", "DOWN"):
            tokens = data.get("tokens", [])
            for token in tokens:
                if token.get("token_id") == winner:
                    winner = (token.get("outcome") or "").upper()
                    break

    final_up_price: Optional[float] = None
    total_volume: Optional[float] = None
    for token in data.get("tokens", []):
        if (token.get("outcome") or "").upper() == "UP":
            try:
                final_up_price = float(token.get("price", 0))
            except (TypeError, ValueError):
                pass

    try:
        total_volume = float(data.get("volume") or data.get("volumeNum") or 0)
    except (TypeError, ValueError):
        pass

    return {
        "resolved": True,
        "winner": winner,
        "final_up_price": final_up_price,
        "total_volume": total_volume,
    }


def fetch_token_ids_sync(condition_id: str, base_url: str | None = None) -> tuple[str, str] | None:
    """Synchronous fetch of token IDs for a market. Used by trading executor."""
    url = base_url or CLOB_REST_BASE
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{url}/markets/{condition_id}")
            resp.raise_for_status()
            data = resp.json()

        if isinstance(data, dict):
            tokens_list = data.get("tokens", [])
            if len(tokens_list) >= 2:
                up_id = down_id = None
                for t in tokens_list:
                    outcome = (t.get("outcome") or "").upper()
                    tid = t.get("token_id", "")
                    if outcome in ("YES", "UP"):
                        up_id = tid
                    elif outcome in ("NO", "DOWN"):
                        down_id = tid
                if not up_id:
                    up_id = tokens_list[0].get("token_id", "")
                if not down_id:
                    down_id = tokens_list[1].get("token_id", "")
                if up_id and down_id:
                    return (up_id, down_id)
    except Exception as e:
        logger.warning("Error fetching token IDs for %s: %s", condition_id[:16], e)
    return None
