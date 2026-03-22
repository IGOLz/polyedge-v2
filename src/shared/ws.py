"""WebSocket connection and message handling for Polymarket CLOB price feed."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from shared.config import POLYMARKET_API

logger = logging.getLogger(__name__)

WS_URL = POLYMARKET_API["clob_ws_url"]
WS_RECV_TIMEOUT = 5.0
WS_APP_PING_INTERVAL = 10.0
_WS_BASE_DELAY = 1.0
_WS_MAX_DELAY = 30.0


@dataclass(frozen=True)
class QuoteUpdate:
    asset_id: str
    best_bid: float | None
    best_ask: float | None
    mid: float | None
    best_bid_size: float | None = None
    best_ask_size: float | None = None
    source_event_type: str = ""


def build_subscription_message(asset_ids: list[str]) -> str:
    """Return a CLOB market subscription message for multiple assets."""
    return json.dumps(
        {
            "type": "market",
            "assets_ids": asset_ids,
            "custom_feature_enabled": True,
        }
    )


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= result <= 1.0:
        return result
    return None


def _midpoint(best_bid, best_ask) -> Optional[float]:
    bid = _safe_float(best_bid)
    ask = _safe_float(best_ask)
    if bid is not None and ask is not None:
        return round((bid + ask) / 2.0, 6)
    return ask if ask is not None else bid


def _safe_size(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _top_book_price(levels, index: int) -> Optional[float]:
    if not isinstance(levels, list) or not levels:
        return None
    first = levels[0]
    if isinstance(first, dict):
        return _safe_float(first.get("price"))
    if isinstance(first, (list, tuple)) and len(first) > index:
        return _safe_float(first[index])
    return None


def _top_book_size(levels) -> Optional[float]:
    if not isinstance(levels, list) or not levels:
        return None
    first = levels[0]
    if isinstance(first, dict):
        return _safe_size(
            first.get("size")
            or first.get("quantity")
            or first.get("amount")
        )
    if isinstance(first, (list, tuple)) and len(first) > 1:
        return _safe_size(first[1])
    return None


def _quote_from_values(
    *,
    asset_id: str,
    best_bid,
    best_ask,
    best_bid_size=None,
    best_ask_size=None,
    source_event_type: str,
) -> QuoteUpdate | None:
    bid = _safe_float(best_bid)
    ask = _safe_float(best_ask)
    mid = _midpoint(bid, ask)
    if bid is None and ask is None and mid is None:
        return None
    return QuoteUpdate(
        asset_id=asset_id,
        best_bid=bid,
        best_ask=ask,
        mid=mid,
        best_bid_size=_safe_size(best_bid_size),
        best_ask_size=_safe_size(best_ask_size),
        source_event_type=source_event_type,
    )


def extract_up_prices(msg: dict, tracked_asset_ids: set[str]) -> dict[str, float]:
    """Parse a WS message and return latest neutral prices for tracked assets."""
    if not isinstance(msg, dict):
        return {}

    event_type = msg.get("event_type", "")
    updates: dict[str, float] = {}

    if event_type == "price_change":
        for entry in msg.get("price_changes") or []:
            if not isinstance(entry, dict):
                continue
            asset_id = entry.get("asset_id")
            if asset_id not in tracked_asset_ids:
                continue
            price = _midpoint(entry.get("best_bid"), entry.get("best_ask"))
            if price is None:
                price = _safe_float(entry.get("price"))
            if price is not None:
                updates[asset_id] = price
        return updates

    asset_id = msg.get("asset_id")
    if asset_id not in tracked_asset_ids:
        return {}

    if event_type == "best_bid_ask":
        price = _midpoint(msg.get("best_bid"), msg.get("best_ask"))
        if price is not None:
            updates[asset_id] = price
        return updates

    if event_type == "book":
        best_bid = _top_book_price(msg.get("bids"), 0)
        best_ask = _top_book_price(msg.get("asks"), 0)
        price = _midpoint(best_bid, best_ask)
        if price is not None:
            updates[asset_id] = price
        return updates

    if event_type == "last_trade_price":
        price = _safe_float(msg.get("price"))
        if price is not None:
            updates[asset_id] = price
        return updates

    return {}


def extract_quote_updates(
    msg: dict,
    tracked_asset_ids: set[str],
) -> dict[str, QuoteUpdate]:
    """Parse a WS message and return best-bid/ask quote updates."""
    if not isinstance(msg, dict):
        return {}

    event_type = msg.get("event_type", "")
    updates: dict[str, QuoteUpdate] = {}

    if event_type == "price_change":
        for entry in msg.get("price_changes") or []:
            if not isinstance(entry, dict):
                continue
            asset_id = entry.get("asset_id")
            if asset_id not in tracked_asset_ids:
                continue
            quote = _quote_from_values(
                asset_id=asset_id,
                best_bid=entry.get("best_bid"),
                best_ask=entry.get("best_ask"),
                best_bid_size=entry.get("best_bid_size")
                or entry.get("bid_size"),
                best_ask_size=entry.get("best_ask_size")
                or entry.get("ask_size"),
                source_event_type=event_type,
            )
            if quote is not None:
                updates[asset_id] = quote
        return updates

    asset_id = msg.get("asset_id")
    if asset_id not in tracked_asset_ids:
        return {}

    if event_type == "best_bid_ask":
        quote = _quote_from_values(
            asset_id=asset_id,
            best_bid=msg.get("best_bid"),
            best_ask=msg.get("best_ask"),
            best_bid_size=msg.get("best_bid_size") or msg.get("bid_size"),
            best_ask_size=msg.get("best_ask_size") or msg.get("ask_size"),
            source_event_type=event_type,
        )
        return {asset_id: quote} if quote is not None else {}

    if event_type == "book":
        quote = _quote_from_values(
            asset_id=asset_id,
            best_bid=_top_book_price(msg.get("bids"), 0),
            best_ask=_top_book_price(msg.get("asks"), 0),
            best_bid_size=_top_book_size(msg.get("bids")),
            best_ask_size=_top_book_size(msg.get("asks")),
            source_event_type=event_type,
        )
        return {asset_id: quote} if quote is not None else {}

    if event_type == "last_trade_price":
        price = _safe_float(msg.get("price"))
        if price is None:
            return {}
        return {
            asset_id: QuoteUpdate(
                asset_id=asset_id,
                best_bid=None,
                best_ask=None,
                mid=price,
                source_event_type=event_type,
            )
        }

    return {}


async def run_websocket_listener(
    get_tracked_markets: Callable,
    on_price_update: Callable,
    shutdown_event: asyncio.Event,
    reconnect_event: asyncio.Event,
    on_connection_state: Optional[Callable] = None,
) -> None:
    """Listen to market data for all tracked markets and route price updates."""
    attempt = 0

    while not shutdown_event.is_set():
        tracked_markets = await get_tracked_markets()
        if not tracked_markets:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            continue

        asset_to_market = {
            up_token_id: market_id
            for market_id, up_token_id, _down_token_id in tracked_markets
            if up_token_id
        }
        asset_ids = sorted(asset_to_market.keys())
        if not asset_ids:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            continue

        force_reconnect = False

        try:
            async with websockets.connect(
                WS_URL,
                ping_interval=None,
                close_timeout=10,
            ) as ws:
                attempt = 0
                await ws.send(build_subscription_message(asset_ids))
                if on_connection_state is not None:
                    await on_connection_state(True, len(asset_ids))
                logger.info("WS subscribed to %d tracked market asset(s)", len(asset_ids))
                reconnect_event.clear()
                last_ping = asyncio.get_running_loop().time()

                while not shutdown_event.is_set():
                    if reconnect_event.is_set():
                        reconnect_event.clear()
                        force_reconnect = True
                        break

                    now_monotonic = asyncio.get_running_loop().time()
                    recv_timeout = max(
                        0.1,
                        min(
                            WS_RECV_TIMEOUT,
                            WS_APP_PING_INTERVAL - (now_monotonic - last_ping),
                        ),
                    )

                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
                    except asyncio.TimeoutError:
                        now_monotonic = asyncio.get_running_loop().time()
                        if now_monotonic - last_ping >= WS_APP_PING_INTERVAL:
                            await ws.send("PING")
                            last_ping = now_monotonic
                        continue

                    if raw == "PONG":
                        continue
                    if raw == "PING":
                        await ws.send("PONG")
                        continue
                    if not raw or raw[0] not in ("{", "["):
                        continue

                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    updates = extract_up_prices(msg, set(asset_ids))
                    for asset_id, price in updates.items():
                        market_id = asset_to_market.get(asset_id)
                        if market_id is not None:
                            await on_price_update(market_id, price)

        except ConnectionClosed as exc:
            if on_connection_state is not None:
                await on_connection_state(False, len(asset_ids))
            logger.info(
                "WS disconnected (code=%s) - retrying (attempt %d)",
                exc.code,
                attempt + 1,
            )
        except Exception as exc:
            if on_connection_state is not None:
                await on_connection_state(False, len(asset_ids))
            logger.error("WS error: %s - retrying (attempt %d)", exc, attempt + 1)

        if shutdown_event.is_set():
            break
        if force_reconnect:
            continue

        delay = min(_WS_BASE_DELAY * (2 ** attempt), _WS_MAX_DELAY)
        attempt += 1
        await asyncio.sleep(delay)


async def run_quote_listener(
    get_tracked_assets: Callable,
    on_quote_update: Callable,
    shutdown_event: asyncio.Event,
    reconnect_event: asyncio.Event,
    on_connection_state: Optional[Callable] = None,
) -> None:
    """Listen to market data and route best-bid/ask updates."""
    attempt = 0

    while not shutdown_event.is_set():
        tracked_assets = await get_tracked_assets()
        if not tracked_assets:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            continue

        asset_lookup = {
            asset["asset_id"]: asset
            for asset in tracked_assets
            if asset.get("asset_id")
        }
        asset_ids = sorted(asset_lookup.keys())
        if not asset_ids:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            continue

        force_reconnect = False
        try:
            async with websockets.connect(
                WS_URL,
                ping_interval=None,
                close_timeout=10,
            ) as ws:
                attempt = 0
                await ws.send(build_subscription_message(asset_ids))
                if on_connection_state is not None:
                    await on_connection_state(True, len(asset_ids))
                reconnect_event.clear()
                last_ping = asyncio.get_running_loop().time()

                while not shutdown_event.is_set():
                    if reconnect_event.is_set():
                        reconnect_event.clear()
                        force_reconnect = True
                        break

                    now_monotonic = asyncio.get_running_loop().time()
                    recv_timeout = max(
                        0.1,
                        min(
                            WS_RECV_TIMEOUT,
                            WS_APP_PING_INTERVAL - (now_monotonic - last_ping),
                        ),
                    )

                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
                    except asyncio.TimeoutError:
                        now_monotonic = asyncio.get_running_loop().time()
                        if now_monotonic - last_ping >= WS_APP_PING_INTERVAL:
                            await ws.send("PING")
                            last_ping = now_monotonic
                        continue

                    if raw == "PONG":
                        continue
                    if raw == "PING":
                        await ws.send("PONG")
                        continue
                    if not raw or raw[0] not in ("{", "["):
                        continue

                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    updates = extract_quote_updates(msg, set(asset_ids))
                    for asset_id, quote in updates.items():
                        asset = asset_lookup.get(asset_id)
                        if asset is not None:
                            await on_quote_update(asset, quote)
        except ConnectionClosed as exc:
            if on_connection_state is not None:
                await on_connection_state(False, len(asset_ids))
            logger.info(
                "Quote WS disconnected (code=%s) - retrying (attempt %d)",
                exc.code,
                attempt + 1,
            )
        except Exception as exc:
            if on_connection_state is not None:
                await on_connection_state(False, len(asset_ids))
            logger.error(
                "Quote WS error: %s - retrying (attempt %d)",
                exc,
                attempt + 1,
            )

        if shutdown_event.is_set():
            break
        if force_reconnect:
            continue

        delay = min(_WS_BASE_DELAY * (2 ** attempt), _WS_MAX_DELAY)
        attempt += 1
        await asyncio.sleep(delay)
