"""WebSocket connection and message handling for Polymarket CLOB price feed.

Used by core for price collection; available for trading for real-time data.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from shared.config import POLYMARKET_API

logger = logging.getLogger(__name__)

WS_URL = POLYMARKET_API["clob_ws_url"]
_WS_BASE_DELAY = 1.0
_WS_MAX_DELAY = 30.0


def build_subscription_message(token_ids: list[str]) -> str:
    """Return a CLOB market subscription message."""
    return json.dumps({"type": "subscribe", "assets_ids": token_ids})


def extract_up_price(msg: dict, up_token_id: str, down_token_id: str) -> Optional[float]:
    """
    Parse a CLOB WS message and return the Up token's price, or None.
    Processes messages where event_type == "price_change" OR price_changes array present.
    """
    event_type = msg.get("event_type", "")
    price_changes = msg.get("price_changes")

    if event_type != "price_change" and not isinstance(price_changes, list):
        return None
    if not isinstance(price_changes, list):
        return None

    for entry in price_changes:
        if not isinstance(entry, dict):
            continue
        token_id = entry.get("asset_id")
        if token_id != up_token_id:
            continue
        price_val = entry.get("best_ask") or entry.get("price")
        if price_val is None:
            continue
        try:
            price = float(price_val)
        except (ValueError, TypeError):
            continue
        if 0.0 <= price <= 1.0:
            return price

    return None


async def run_websocket_listener(
    get_active_market: Callable,
    on_price_update: Callable,
    shutdown_event: asyncio.Event,
    reconnect_event: asyncio.Event,
) -> None:
    """
    Generic WebSocket listener that:
    - Calls get_active_market() to get the current market's token IDs
    - Calls on_price_update(market_id, price) on each price change
    - Reconnects on reconnect_event or connection error

    This is decoupled from AppState so it can be used by both core and trading.
    """
    attempt = 0

    while not shutdown_event.is_set():
        force_reconnect = False

        try:
            async with websockets.connect(
                WS_URL,
                ping_interval=None,
                close_timeout=10,
            ) as ws:
                attempt = 0

                market_info = await get_active_market()
                if market_info:
                    mid, up_token, down_token = market_info
                    await ws.send(build_subscription_message([up_token, down_token]))
                    logger.info("WS subscribed to market %s", mid[:16] if mid else "—")
                else:
                    mid = up_token = down_token = None

                reconnect_event.clear()

                while not shutdown_event.is_set():
                    if reconnect_event.is_set():
                        reconnect_event.clear()
                        force_reconnect = True
                        break

                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    except asyncio.TimeoutError:
                        continue

                    if not raw or raw[0] not in ('{', '['):
                        continue
                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    if not isinstance(msg, dict) or up_token is None:
                        continue

                    price = extract_up_price(msg, up_token, down_token)
                    if price is not None:
                        await on_price_update(mid, price)

        except ConnectionClosed as exc:
            logger.info("WS disconnected (code=%s) — retrying (attempt %d)", exc.code, attempt + 1)
        except Exception as exc:
            logger.error("WS error: %s — retrying (attempt %d)", exc, attempt + 1)

        if shutdown_event.is_set():
            break
        if force_reconnect:
            continue

        delay = min(_WS_BASE_DELAY * (2 ** attempt), _WS_MAX_DELAY)
        attempt += 1
        await asyncio.sleep(delay)
