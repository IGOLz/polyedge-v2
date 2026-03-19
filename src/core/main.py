"""Entry point for the Polymarket short-duration crypto market tracker."""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from shared import db
from shared.api import (
    fetch_market_resolution,
    fetch_open_crypto_market_volumes,
    fetch_open_crypto_markets,
)
from shared.config import CORE_RUNTIME, TIMING
from shared.logging import setup_logger
from shared.models import MarketState
from shared.ws import run_websocket_listener

logger = setup_logger("core")

MARKET_DISCOVERY_INTERVAL = TIMING["market_discovery_interval"]
PRICE_RECORD_INTERVAL = TIMING["price_record_interval"]
VOLUME_POLL_INTERVAL = TIMING["volume_poll_interval"]
HEARTBEAT_INTERVAL = TIMING["heartbeat_interval"]
RESOLUTION_POLL_INTERVAL = TIMING["resolution_poll_interval"]
CORE_DEBUG_MODE = CORE_RUNTIME["debug_mode"]


def _short(mid: str) -> str:
    return f"{mid[:6]}...{mid[-3:]}" if len(mid) > 9 else mid


def _win(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%H:%M')}->{end.strftime('%H:%M')}"


def _market_total_seconds(state: MarketState) -> int:
    return max(0, int((state.ended_at - state.started_at).total_seconds()))


@dataclass
class AppState:
    markets: dict[str, MarketState] = field(default_factory=dict)
    markets_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    ws_reconnect_event: asyncio.Event = field(default_factory=asyncio.Event)
    ws_connected: bool = False
    ws_connection_count: int = 0
    ws_message_count: int = 0
    ws_last_message_at: Optional[datetime] = None


async def _upsert_market_outcome(**kwargs) -> None:
    if CORE_DEBUG_MODE:
        market_id = kwargs.get("market_id", "")
        logger.info("Debug mode: skipped market_outcomes write for %s", _short(market_id))
        return
    await db.upsert_market_outcome(**kwargs)


async def _insert_tick(
    *,
    second: int,
    tick_time: datetime,
    market_id: str,
    market_type: str | None,
    up_price: float,
    volume: float | None,
) -> None:
    if CORE_DEBUG_MODE:
        logger.info(
            "Debug mode: would write tick market=%s type=%s time=%s second=%s up_price=%.4f volume=%s",
            _short(market_id),
            market_type or "unknown",
            tick_time.isoformat(),
            second,
            up_price,
            "None" if volume is None else f"{volume:.4f}",
        )
        return
    await db.insert_tick(
        time=tick_time,
        market_id=market_id,
        up_price=up_price,
        volume=volume,
    )


async def market_discovery_loop(
    app_state: AppState, http_client: httpx.AsyncClient
) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            discovered_markets = await fetch_open_crypto_markets(http_client)
        except Exception as exc:
            logger.error("Market discovery error: %s", exc)
            discovered_markets = []

        needs_reconnect = False
        for discovered in discovered_markets:
            is_new = False
            async with app_state.markets_lock:
                existing = app_state.markets.get(discovered.market_id)
                if existing is None:
                    app_state.markets[discovered.market_id] = discovered
                    is_new = True
                    needs_reconnect = True
                else:
                    if (
                        existing.up_token_id != discovered.up_token_id
                        or existing.down_token_id != discovered.down_token_id
                    ):
                        needs_reconnect = True
                    existing.up_token_id = discovered.up_token_id
                    existing.down_token_id = discovered.down_token_id
                    existing.market_type = discovered.market_type
                    existing.started_at = discovered.started_at
                    existing.ended_at = discovered.ended_at
                    if existing.latest_up_price is None and discovered.latest_up_price is not None:
                        existing.latest_up_price = discovered.latest_up_price
                    if existing.last_emitted_up_price is None and discovered.latest_up_price is not None:
                        existing.last_emitted_up_price = discovered.latest_up_price

            await _upsert_market_outcome(
                market_id=discovered.market_id,
                market_type=discovered.market_type,
                started_at=discovered.started_at,
                ended_at=discovered.ended_at,
            )
            if is_new:
                logger.info(
                    "Tracking %s %s %s",
                    discovered.market_type or "market",
                    _short(discovered.market_id),
                    _win(discovered.started_at, discovered.ended_at),
                )

        if needs_reconnect:
            app_state.ws_reconnect_event.set()

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(), timeout=MARKET_DISCOVERY_INTERVAL
            )
        except asyncio.TimeoutError:
            pass


async def websocket_listener(app_state: AppState) -> None:
    async def get_tracked_markets():
        async with app_state.markets_lock:
            return [
                (market_id, state.up_token_id, state.down_token_id)
                for market_id, state in app_state.markets.items()
                if state.is_open
            ]

    async def on_connection_state(connected: bool, asset_count: int):
        app_state.ws_connected = connected
        if connected:
            app_state.ws_connection_count += 1
            logger.info(
                "WebSocket connected: subscribed to %d asset(s) across %d market(s)",
                asset_count,
                len(app_state.markets),
            )
        else:
            logger.warning("WebSocket disconnected; waiting to reconnect...")

    async def on_price_update(market_id: str, price: float):
        observed_at = datetime.now(timezone.utc)
        app_state.ws_message_count += 1
        app_state.ws_last_message_at = observed_at

        async with app_state.markets_lock:
            state = app_state.markets.get(market_id)
            if state is None or not state.is_open:
                return

            is_first_ws_price = state.latest_up_price is None
            state.latest_up_price = price
            state.latest_up_price_at = observed_at

            if observed_at < state.started_at:
                if is_first_ws_price:
                    logger.info(
                        "WebSocket data ok for %s: first price %.4f arrived before market start",
                        _short(market_id),
                        price,
                    )
                return

            elapsed_second = int((observed_at - state.started_at).total_seconds())
            total_seconds = _market_total_seconds(state)
            if 0 <= elapsed_second < total_seconds:
                state.observed_prices_by_second[elapsed_second] = price
            if is_first_ws_price:
                logger.info(
                    "WebSocket data ok for %s: first live price %.4f at +%ss",
                    _short(market_id),
                    price,
                    max(0, elapsed_second),
                )

    await run_websocket_listener(
        get_tracked_markets=get_tracked_markets,
        on_price_update=on_price_update,
        on_connection_state=on_connection_state,
        shutdown_event=app_state.shutdown_event,
        reconnect_event=app_state.ws_reconnect_event,
    )


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

            total_seconds = _market_total_seconds(state)
            if total_seconds <= 0:
                continue
            if now < state.started_at:
                continue

            current_second = min(
                total_seconds - 1,
                int((min(now, state.ended_at) - state.started_at).total_seconds()),
            )

            if (
                state.last_emitted_up_price is None
                and state.latest_up_price is not None
                and (state.latest_up_price_at is None or state.latest_up_price_at <= state.started_at)
            ):
                state.last_emitted_up_price = state.latest_up_price

            second = state.last_recorded_second + 1
            while second <= current_second:
                observed_price = state.observed_prices_by_second.pop(second, None)
                if observed_price is not None:
                    state.last_emitted_up_price = observed_price

                if state.last_emitted_up_price is None:
                    future_known_seconds = [
                        known_second
                        for known_second in state.observed_prices_by_second.keys()
                        if second < known_second <= current_second
                    ]
                    if not future_known_seconds:
                        break
                    state.last_recorded_second = min(future_known_seconds) - 1
                    second = state.last_recorded_second + 1
                    continue

                tick_time = state.started_at + timedelta(seconds=second)
                await _insert_tick(
                    second=second,
                    tick_time=tick_time,
                    market_id=market_id,
                    market_type=state.market_type,
                    up_price=state.last_emitted_up_price,
                    volume=state.latest_volume,
                )
                state.tick_count += 1
                state.last_recorded_second = second
                state.last_recorded_at = tick_time
                second += 1

            if now >= state.ended_at:
                async with app_state.markets_lock:
                    tracked = app_state.markets.get(market_id)
                    if tracked is not None:
                        tracked.is_open = False
                        tracked.awaiting_resolution = True
                logger.info(
                    "%s %s ended - %d ticks collected",
                    _short(market_id),
                    _win(state.started_at, state.ended_at),
                    state.tick_count,
                )

        if heartbeat_counter >= HEARTBEAT_INTERVAL:
            tracked_count = sum(1 for _, state in snapshot if state.is_open)
            live_count = sum(
                1
                for _, state in snapshot
                if state.is_open and state.started_at <= now < state.ended_at
            )
            ws_age = None
            if app_state.ws_last_message_at is not None:
                ws_age = int((now - app_state.ws_last_message_at).total_seconds())
            logger.info(
                "Heartbeat - tracking %d market(s), live %d, ws_connected=%s, ws_connections=%d, ws_messages=%d, last_ws_update_age=%ss",
                tracked_count,
                live_count,
                app_state.ws_connected,
                app_state.ws_connection_count,
                app_state.ws_message_count,
                "n/a" if ws_age is None else ws_age,
            )
            heartbeat_counter = 0

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(), timeout=PRICE_RECORD_INTERVAL
            )
        except asyncio.TimeoutError:
            pass


async def _poll_resolution(
    app_state: AppState,
    http_client: httpx.AsyncClient,
    market_id: str,
    market_type: Optional[str],
    started_at: datetime,
    ended_at: Optional[datetime],
) -> None:
    while not app_state.shutdown_event.is_set():
        result = await fetch_market_resolution(http_client, market_id)
        if result and result.get("resolved"):
            win_str = _win(started_at, ended_at) if ended_at else started_at.strftime("%H:%M")
            logger.info("%s %s resolved: %s", _short(market_id), win_str, result["winner"])
            await _upsert_market_outcome(
                market_id=market_id,
                market_type=market_type,
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


async def volume_refresh_loop(
    app_state: AppState, http_client: httpx.AsyncClient
) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            latest_volumes = await fetch_open_crypto_market_volumes(http_client)
        except Exception as exc:
            logger.error("Volume refresh error: %s", exc)
            latest_volumes = {}

        updated_count = 0
        async with app_state.markets_lock:
            for market_id, volume in latest_volumes.items():
                state = app_state.markets.get(market_id)
                if state is None:
                    continue
                if state.latest_volume != volume:
                    updated_count += 1
                state.latest_volume = volume

        if CORE_DEBUG_MODE and latest_volumes:
            logger.info(
                "Volume refresh: updated %d tracked market(s) from Polymarket API",
                updated_count,
            )

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(), timeout=VOLUME_POLL_INTERVAL
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
                task = asyncio.create_task(
                    _poll_resolution(
                        app_state,
                        http_client,
                        market_id,
                        state.market_type,
                        state.started_at,
                        state.ended_at,
                    ),
                    name=f"resolve-{market_id}",
                )
                task.add_done_callback(lambda _task, mid=market_id: pending_resolution.discard(mid))

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(), timeout=RESOLUTION_POLL_INTERVAL
            )
        except asyncio.TimeoutError:
            pass


async def recover_unresolved_markets(
    app_state: AppState, http_client: httpx.AsyncClient
) -> None:
    if CORE_DEBUG_MODE:
        logger.info("Debug mode: skipping unresolved market recovery from database.")
        return
    unresolved = await db.fetch_unresolved_markets()
    if not unresolved:
        return
    logger.info("Recovering %d unresolved market(s) from previous run.", len(unresolved))
    for row in unresolved:
        asyncio.create_task(
            _poll_resolution(
                app_state,
                http_client,
                row["market_id"],
                row.get("market_type"),
                row["started_at"],
                row.get("ended_at"),
            ),
            name=f"recover-{row['market_id']}",
        )


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, app_state: AppState) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, app_state.shutdown_event.set)
        except NotImplementedError:
            signal.signal(
                sig,
                lambda *_args: loop.call_soon_threadsafe(app_state.shutdown_event.set),
            )


async def main() -> None:
    mode_label = "DEBUG" if CORE_DEBUG_MODE else "LIVE"
    logger.info("Polymarket crypto 5m/15m tracker starting in %s mode...", mode_label)

    if CORE_DEBUG_MODE:
        logger.warning(
            "Debug mode is ON: websocket/discovery/resolution checks will run, but no database reads or writes will happen."
        )
    else:
        await db.init_pool()
        await db.create_core_tables()

    app_state = AppState()
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, app_state)

    async with httpx.AsyncClient() as http_client:
        await recover_unresolved_markets(app_state, http_client)

        tasks = [
            asyncio.create_task(
                market_discovery_loop(app_state, http_client), name="discovery"
            ),
            asyncio.create_task(websocket_listener(app_state), name="ws-listener"),
            asyncio.create_task(
                price_recorder_loop(app_state), name="price-recorder"
            ),
            asyncio.create_task(
                volume_refresh_loop(app_state, http_client), name="volume-refresh"
            ),
            asyncio.create_task(
                resolution_watcher_loop(app_state, http_client),
                name="resolution-watcher",
            ),
        ]

        await app_state.shutdown_event.wait()
        logger.info("Shutting down...")

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if not CORE_DEBUG_MODE:
        await db.close_pool()
    logger.info("Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
