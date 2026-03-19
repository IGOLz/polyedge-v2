"""WebSocket connection and message handling for Polymarket CLOB price feed."""

from __future__ import annotations

import asyncio
import json
import logging
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
        return (bid + ask) / 2.0
    return ask if ask is not None else bid


def _top_book_price(levels, index: int) -> Optional[float]:
    if not isinstance(levels, list) or not levels:
        return None
    first = levels[0]
    if isinstance(first, dict):
        return _safe_float(first.get("price"))
    if isinstance(first, (list, tuple)) and len(first) > index:
        return _safe_float(first[index])
    return None


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
