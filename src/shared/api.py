"""Polymarket API calls for discovery, enrichment, and resolution polling."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from shared.config import POLYMARKET_API
from shared.models import MarketState

logger = logging.getLogger(__name__)

CLOB_REST_BASE = POLYMARKET_API["clob_rest_base"]
GAMMA_API_BASE = POLYMARKET_API["gamma_api_base"]
DISCOVERY_LOOKAHEAD = timedelta(minutes=20)
SUPPORTED_DURATIONS = (5, 15)
ASSET_CONFIG = {
    "BTC": {"tag_slugs": ("bitcoin", "btc"), "keywords": ("btc", "bitcoin")},
    "ETH": {"tag_slugs": ("ethereum", "eth"), "keywords": ("eth", "ethereum")},
    "XRP": {"tag_slugs": ("ripple", "xrp"), "keywords": ("xrp", "ripple")},
    "SOL": {"tag_slugs": ("solana", "sol"), "keywords": ("sol", "solana")},
}


def _short(mid: str) -> str:
    return f"{mid[:6]}...{mid[-3:]}" if len(mid) > 9 else mid


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _extract_market_volume(data: dict) -> Optional[float]:
    if not isinstance(data, dict):
        return None
    return (
        _safe_float(data.get("volume"))
        or _safe_float(data.get("volumeNum"))
        or _safe_float(data.get("volume_num"))
    )


def _normalize_text(*parts: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", " ".join(parts).lower()).strip()


def _detect_asset(*parts: str) -> Optional[str]:
    normalized = _normalize_text(*parts)
    tokens = set(normalized.split())
    for asset, config in ASSET_CONFIG.items():
        if any(keyword in tokens for keyword in config["keywords"]):
            return asset
    return None


def _detect_duration(*parts: str) -> Optional[int]:
    normalized = _normalize_text(*parts)
    tokens = set(normalized.split())
    if "15m" in tokens or ("15" in tokens and {"min", "minute", "minutes"} & tokens):
        return 15
    if "5m" in tokens or ("5" in tokens and {"min", "minute", "minutes"} & tokens):
        return 5
    return None


def _is_up_down_market(*parts: str) -> bool:
    raw = " ".join(part.lower() for part in parts if part)
    normalized = _normalize_text(*parts)
    tokens = set(normalized.split())
    return (
        "updown" in normalized
        or "up or down" in raw
        or "up-or-down" in raw
        or ("up" in tokens and "down" in tokens)
    )


def _normalize_resolution_outcome(raw_winner: str | None) -> Optional[str]:
    if not raw_winner:
        return None
    winner = raw_winner.strip().upper()
    if winner in {"UP", "YES"}:
        return "Up"
    if winner in {"DOWN", "NO"}:
        return "Down"
    return None


def _extract_resolution_details(data: dict) -> Optional[dict]:
    if not isinstance(data, dict):
        return None

    tokens = data.get("tokens", [])
    if not isinstance(tokens, list):
        tokens = []

    winner = _normalize_resolution_outcome(data.get("winner") or data.get("outcome"))
    resolution_source: Optional[str] = "top_level" if winner else None

    if winner is None:
        winning_token_id = str(data.get("winner") or "").strip()
        for token in tokens:
            if token.get("token_id") == winning_token_id:
                winner = _normalize_resolution_outcome(token.get("outcome"))
                if winner is not None:
                    resolution_source = "winner_token_id"
                    break

    if winner is None:
        for token in tokens:
            if token.get("winner") is True:
                winner = _normalize_resolution_outcome(token.get("outcome"))
                if winner is not None:
                    resolution_source = "token_flag"
                    break

    is_resolved = bool(data.get("resolved", False)) or winner is not None
    if not is_resolved or winner is None:
        return None

    final_up_price: Optional[float] = None
    for token in tokens:
        if (token.get("outcome") or "").upper() in {"UP", "YES"}:
            up_price = _safe_float(token.get("price"))
            if up_price is not None:
                final_up_price = up_price
            break

    total_volume = _extract_market_volume(data)

    return {
        "resolved": True,
        "winner": winner,
        "final_up_price": final_up_price,
        "total_volume": total_volume,
        "resolution_source": resolution_source or "unknown",
    }


async def enrich_with_clob(
    client: httpx.AsyncClient,
    market_id: str,
    market_type: str,
    started_at: datetime,
    ended_at: datetime,
    initial_volume: Optional[float] = None,
) -> Optional[MarketState]:
    """Fetch token IDs and seed price information from the CLOB market endpoint."""
    try:
        resp = await client.get(f"{CLOB_REST_BASE}/markets/{market_id}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("CLOB enrich failed - %s: %s", _short(market_id), exc)
        return None

    tokens = data.get("tokens", [])
    if len(tokens) < 2:
        return None

    up_token_id: Optional[str] = None
    down_token_id: Optional[str] = None
    initial_up_price: Optional[float] = None

    for token in tokens:
        outcome = (token.get("outcome") or "").upper()
        token_id = token.get("token_id")
        if outcome in {"UP", "YES"}:
            up_token_id = token_id
            initial_up_price = _safe_float(
                token.get("price")
                or token.get("last_trade_price")
                or token.get("lastTradePrice")
            )
        elif outcome in {"DOWN", "NO"}:
            down_token_id = token_id

    if not up_token_id or not down_token_id:
        up_token_id = tokens[0].get("token_id")
        down_token_id = tokens[1].get("token_id")
        if initial_up_price is None:
            initial_up_price = _safe_float(
                tokens[0].get("price")
                or tokens[0].get("last_trade_price")
                or tokens[0].get("lastTradePrice")
            )

    if not up_token_id or not down_token_id:
        return None

    return MarketState(
        market_id=market_id,
        up_token_id=up_token_id,
        down_token_id=down_token_id,
        started_at=started_at,
        ended_at=ended_at,
        market_type=market_type,
        latest_up_price=initial_up_price,
        latest_volume=initial_volume,
        last_emitted_up_price=initial_up_price,
    )


async def _fetch_events_for_tag(
    client: httpx.AsyncClient,
    tag_slug: str,
) -> list[dict]:
    try:
        resp = await client.get(
            f"{GAMMA_API_BASE}/events",
            params={
                "active": "true",
                "archived": "false",
                "closed": "false",
                "tag_slug": tag_slug,
                "order": "volume24hr",
                "ascending": "false",
                "limit": "200",
            },
            timeout=15,
        )
        resp.raise_for_status()
        events = resp.json()
    except Exception as exc:
        logger.error("Gamma API error for tag %s: %s", tag_slug, exc)
        return []

    if isinstance(events, dict):
        events = events.get("data", [])
    return events if isinstance(events, list) else []


async def fetch_open_crypto_markets(client: httpx.AsyncClient) -> list[MarketState]:
    """Fetch tracked crypto up/down markets for BTC, ETH, XRP, and SOL."""
    now = datetime.now(timezone.utc)
    events_by_id: dict[str, dict] = {}

    for config in ASSET_CONFIG.values():
        for tag_slug in config["tag_slugs"]:
            for event in await _fetch_events_for_tag(client, tag_slug):
                event_id = str(event.get("id") or event.get("slug") or "")
                if event_id:
                    events_by_id[event_id] = event

    candidates: list[tuple[str, str, datetime, datetime]] = []
    seen_market_ids: set[str] = set()

    for event in events_by_id.values():
        markets = event.get("markets") or []
        series_list = event.get("series") or []
        series_text = " ".join((s.get("slug") or "") for s in series_list)
        event_slug = event.get("slug") or ""
        event_title = event.get("title") or event.get("name") or ""

        for market in markets:
            slug = market.get("slug") or ""
            question = market.get("question") or ""
            combined_parts = (slug, question, event_slug, event_title, series_text)

            asset = _detect_asset(*combined_parts)
            if asset not in ASSET_CONFIG:
                continue
            duration = _detect_duration(*combined_parts)
            if duration not in SUPPORTED_DURATIONS:
                continue
            if not _is_up_down_market(*combined_parts):
                continue
            if market.get("closed", False):
                continue

            market_id = market.get("conditionId") or market.get("condition_id")
            if not market_id or market_id in seen_market_ids:
                continue

            end_str = market.get("endDate") or market.get("end_date")
            if not end_str:
                continue
            try:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            start_dt = end_dt - timedelta(minutes=duration)
            if end_dt <= now:
                continue
            if start_dt > now + DISCOVERY_LOOKAHEAD:
                continue

            seen_market_ids.add(market_id)
            candidates.append(
                (
                    market_id,
                    f"{asset}_{duration}m",
                    start_dt,
                    end_dt,
                    _extract_market_volume(market),
                )
            )

    if not candidates:
        return []

    enriched = await asyncio.gather(
        *[
            enrich_with_clob(
                client,
                market_id,
                market_type,
                started_at,
                ended_at,
                initial_volume,
            )
            for market_id, market_type, started_at, ended_at, initial_volume in candidates
        ],
        return_exceptions=True,
    )

    results: list[MarketState] = []
    for item in enriched:
        if isinstance(item, Exception):
            logger.error("Market enrichment task failed: %s", item)
            continue
        if item is not None:
            results.append(item)

    results.sort(key=lambda state: (state.started_at, state.ended_at, state.market_type or ""))
    return results


async def fetch_open_btc_5min_markets(client: httpx.AsyncClient) -> list[MarketState]:
    """Backward-compatible wrapper around the generic crypto market discovery."""
    markets = await fetch_open_crypto_markets(client)
    return [market for market in markets if market.market_type == "BTC_5m"]


async def fetch_open_crypto_market_volumes(client: httpx.AsyncClient) -> dict[str, float]:
    """Fetch the latest cumulative volume for currently open tracked crypto markets."""
    now = datetime.now(timezone.utc)
    volumes: dict[str, float] = {}

    for config in ASSET_CONFIG.values():
        for tag_slug in config["tag_slugs"]:
            for event in await _fetch_events_for_tag(client, tag_slug):
                markets = event.get("markets") or []
                series_list = event.get("series") or []
                series_text = " ".join((s.get("slug") or "") for s in series_list)
                event_slug = event.get("slug") or ""
                event_title = event.get("title") or event.get("name") or ""

                for market in markets:
                    slug = market.get("slug") or ""
                    question = market.get("question") or ""
                    combined_parts = (slug, question, event_slug, event_title, series_text)

                    asset = _detect_asset(*combined_parts)
                    if asset not in ASSET_CONFIG:
                        continue
                    duration = _detect_duration(*combined_parts)
                    if duration not in SUPPORTED_DURATIONS:
                        continue
                    if not _is_up_down_market(*combined_parts):
                        continue
                    if market.get("closed", False):
                        continue

                    market_id = market.get("conditionId") or market.get("condition_id")
                    if not market_id:
                        continue

                    end_str = market.get("endDate") or market.get("end_date")
                    if not end_str:
                        continue
                    try:
                        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue

                    if end_dt <= now:
                        continue

                    volume = _extract_market_volume(market)
                    if volume is not None:
                        volumes[market_id] = volume

    return volumes


async def fetch_market_resolution(
    client: httpx.AsyncClient, market_id: str
) -> Optional[dict]:
    """Fetch resolution data for a single market."""
    try:
        resp = await client.get(f"{CLOB_REST_BASE}/markets/{market_id}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("Resolution fetch failed - %s: %s", _short(market_id), exc)
        return None

    return _extract_resolution_details(data)


def fetch_token_ids_sync(
    condition_id: str, base_url: str | None = None
) -> tuple[str, str] | None:
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
                for token in tokens_list:
                    outcome = (token.get("outcome") or "").upper()
                    token_id = token.get("token_id", "")
                    if outcome in {"YES", "UP"}:
                        up_id = token_id
                    elif outcome in {"NO", "DOWN"}:
                        down_id = token_id
                if not up_id:
                    up_id = tokens_list[0].get("token_id", "")
                if not down_id:
                    down_id = tokens_list[1].get("token_id", "")
                if up_id and down_id:
                    return (up_id, down_id)
    except Exception as exc:
        logger.warning("Error fetching token IDs for %s: %s", condition_id[:16], exc)
    return None
