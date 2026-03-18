"""
Entry point for the Polymarket BTC 5-minute market tracker (core service).

Three concurrent async tasks:
  1. market_discovery_loop  — polls REST API every 30s, registers new markets
  2. websocket_listener     — maintains WS connection, routes price updates
  3. price_recorder_loop    — every 1s, flushes latest prices to DB

Plus a resolution_loop that watches expired markets until they resolve.
"""

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from shared import db
from shared.api import fetch_open_btc_5min_markets, fetch_market_resolution
from shared.config import TIMING
from shared.logging import setup_logger
from shared.models import MarketState
from shared.ws import run_websocket_listener

logger = setup_logger("core")

MARKET_DISCOVERY_INTERVAL = TIMING["market_discovery_interval"]
PRICE_RECORD_INTERVAL = TIMING["price_record_interval"]
HEARTBEAT_INTERVAL = TIMING["heartbeat_interval"]
RESOLUTION_POLL_INTERVAL = TIMING["resolution_poll_interval"]


def _short(mid: str) -> str:
    return f"{mid[:6]}...{mid[-3:]}" if len(mid) > 9 else mid


def _win(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%H:%M')}→{end.strftime('%H:%M')}"


# ---------------------------------------------------------------------------
# Shared application state
# ---------------------------------------------------------------------------
@dataclass
class AppState:
    markets: dict[str, MarketState] = field(default_factory=dict)
    markets_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    ws_reconnect_event: asyncio.Event = field(default_factory=asyncio.Event)


# ---------------------------------------------------------------------------
# Task 1: Market discovery
# ---------------------------------------------------------------------------
async def market_discovery_loop(app_state: AppState, http_client: httpx.AsyncClient) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            open_markets = await fetch_open_btc_5min_markets(http_client)
        except Exception as exc:
            logger.error("Market discovery error: %s", exc)
            open_markets = []

        async with app_state.markets_lock:
            known_ids = set(app_state.markets.keys())

        for state in open_markets:
            if state.market_id not in known_ids:
                async with app_state.markets_lock:
                    app_state.markets[state.market_id] = state

                await db.upsert_market_outcome(
                    market_id=state.market_id,
                    started_at=state.started_at,
                    ended_at=state.ended_at,
                )
                app_state.ws_reconnect_event.set()

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(), timeout=MARKET_DISCOVERY_INTERVAL
            )
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Task 2: WebSocket listener (uses shared WS module)
# ---------------------------------------------------------------------------
async def websocket_listener(app_state: AppState) -> None:
    async def get_active_market():
        async with app_state.markets_lock:
            for mid, state in app_state.markets.items():
                if state.is_open:
                    return (mid, state.up_token_id, state.down_token_id)
        return None

    async def on_price_update(market_id, price):
        async with app_state.markets_lock:
            state = app_state.markets.get(market_id)
            if state is not None and state.is_open:
                state.latest_up_price = price

    await run_websocket_listener(
        get_active_market=get_active_market,
        on_price_update=on_price_update,
        shutdown_event=app_state.shutdown_event,
        reconnect_event=app_state.ws_reconnect_event,
    )


# ---------------------------------------------------------------------------
# Task 3: Price recorder
# ---------------------------------------------------------------------------
async def price_recorder_loop(app_state: AppState) -> None:
    heartbeat_counter = 0

    while not app_state.shutdown_event.is_set():
        now = datetime.now(timezone.utc)
        heartbeat_counter += PRICE_RECORD_INTERVAL

        async with app_state.markets_lock:
            snapshot = list(app_state.markets.items())

        for market_id, state in snapshot:
            if not state.is_open:
                continue

            if now >= state.ended_at:
                async with app_state.markets_lock:
                    if market_id in app_state.markets:
                        app_state.markets[market_id].is_open = False
                        app_state.markets[market_id].awaiting_resolution = True
                logger.info(
                    "⏹️  %s  %s  ended — %d ticks collected",
                    _short(market_id), _win(state.started_at, state.ended_at), state.tick_count,
                )
                continue

            if state.latest_up_price is None:
                continue

            await db.insert_tick(
                time=now,
                market_id=market_id,
                up_price=state.latest_up_price,
                volume=state.latest_volume,
            )
            state.tick_count += 1

        if heartbeat_counter >= HEARTBEAT_INTERVAL:
            active = [(mid, st) for mid, st in snapshot if st.is_open and st.latest_up_price is not None]
            if active:
                mid, st = active[0]
                logger.info("💓 Heartbeat — tracking: %s  %s", _short(mid), _win(st.started_at, st.ended_at))
            else:
                logger.info("💓 Heartbeat — no active market")
            heartbeat_counter = 0

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(), timeout=PRICE_RECORD_INTERVAL
            )
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Resolution poller
# ---------------------------------------------------------------------------
async def _poll_resolution(
    app_state: AppState,
    http_client: httpx.AsyncClient,
    market_id: str,
    started_at: datetime,
    ended_at: Optional[datetime],
) -> None:
    while not app_state.shutdown_event.is_set():
        result = await fetch_market_resolution(http_client, market_id)
        if result and result.get("resolved"):
            win_str = _win(started_at, ended_at) if ended_at else started_at.strftime("%H:%M")
            logger.info("✅ %s  %s  resolved: %s", _short(market_id), win_str, result["winner"])
            await db.upsert_market_outcome(
                market_id=market_id,
                started_at=started_at,
                ended_at=ended_at,
                final_outcome=result["winner"],
                final_up_price=result["final_up_price"],
                total_volume=result["total_volume"],
                resolved=True,
            )
            async with app_state.markets_lock:
                app_state.markets.pop(market_id, None)
            return

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(), timeout=RESOLUTION_POLL_INTERVAL
            )
        except asyncio.TimeoutError:
            pass


async def resolution_watcher_loop(
    app_state: AppState, http_client: httpx.AsyncClient
) -> None:
    pending_resolution: set[str] = set()

    while not app_state.shutdown_event.is_set():
        async with app_state.markets_lock:
            snapshot = list(app_state.markets.items())

        for market_id, state in snapshot:
            if state.awaiting_resolution and market_id not in pending_resolution:
                pending_resolution.add(market_id)
                asyncio.create_task(
                    _poll_resolution(
                        app_state, http_client, market_id,
                        state.started_at, state.ended_at,
                    ),
                    name=f"resolve-{market_id}",
                )

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(), timeout=RESOLUTION_POLL_INTERVAL
            )
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Startup: recover unresolved markets from previous runs
# ---------------------------------------------------------------------------
async def recover_unresolved_markets(
    app_state: AppState, http_client: httpx.AsyncClient
) -> None:
    unresolved = await db.fetch_unresolved_markets()
    if not unresolved:
        return
    logger.info("Recovering %d unresolved market(s) from previous run.", len(unresolved))
    for row in unresolved:
        asyncio.create_task(
            _poll_resolution(
                app_state, http_client,
                row["market_id"], row["started_at"], row.get("ended_at"),
            ),
            name=f"recover-{row['market_id']}",
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    logger.info("Polymarket BTC 5-minute tracker starting...")

    await db.init_pool()
    await db.create_core_tables()

    app_state = AppState()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: app_state.shutdown_event.set())

    async with httpx.AsyncClient() as http_client:
        await recover_unresolved_markets(app_state, http_client)

        tasks = [
            asyncio.create_task(market_discovery_loop(app_state, http_client), name="discovery"),
            asyncio.create_task(websocket_listener(app_state), name="ws-listener"),
            asyncio.create_task(price_recorder_loop(app_state), name="price-recorder"),
            asyncio.create_task(resolution_watcher_loop(app_state, http_client), name="resolution-watcher"),
        ]

        await app_state.shutdown_event.wait()
        logger.info("Shutting down...")

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    await db.close_pool()
    logger.info("Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
