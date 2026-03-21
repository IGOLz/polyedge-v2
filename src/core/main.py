"""Entry point for the Polymarket short-duration crypto market tracker."""

from __future__ import annotations

import asyncio
import json
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from shared import db
from shared.api import (
    fetch_market_resolution,
    fetch_open_crypto_market_volumes,
    fetch_open_crypto_markets,
)
from shared.binance import (
    CryptoPriceBar,
    build_combined_kline_stream_url,
    current_bar_open_time,
    fetch_rest_klines,
    fill_missing_bars,
    parse_ws_kline_message,
    split_symbol,
)
from shared.config import BINANCE_CONFIG, CORE_RUNTIME, TIMING
from shared.http import get_async_http_client
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
BINANCE_TRACKED_SYMBOLS = [symbol.upper() for symbol in BINANCE_CONFIG["tracked_symbols"]]
BINANCE_BACKFILL_LOOKBACK_SECONDS = BINANCE_CONFIG["backfill_lookback_seconds"]


def _short(mid: str) -> str:
    return f"{mid[:6]}...{mid[-3:]}" if len(mid) > 9 else mid


def _win(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%H:%M')}->{end.strftime('%H:%M')}"


def _market_total_seconds(state: MarketState) -> int:
    return max(0, int((state.ended_at - state.started_at).total_seconds()))


@dataclass
class BinanceSymbolState:
    symbol: str
    asset: str
    quote_asset: str
    last_bar_time: Optional[datetime] = None
    last_close: Optional[float] = None
    last_source: Optional[str] = None


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
    binance_symbols: dict[str, BinanceSymbolState] = field(default_factory=lambda: _build_binance_symbol_states())
    binance_ws_connected: bool = False
    binance_connection_count: int = 0
    binance_reconnect_count: int = 0
    binance_message_count: int = 0
    binance_last_message_at: Optional[datetime] = None


def _build_binance_symbol_states() -> dict[str, BinanceSymbolState]:
    return {
        symbol: BinanceSymbolState(
            symbol=symbol,
            asset=split_symbol(symbol)[0],
            quote_asset=split_symbol(symbol)[1],
        )
        for symbol in BINANCE_TRACKED_SYMBOLS
    }


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


async def _upsert_crypto_bars(
    app_state: AppState,
    bars: list[CryptoPriceBar],
) -> None:
    if not bars:
        return

    if CORE_DEBUG_MODE:
        logger.info(
            "Debug mode: skipped %d crypto bar write(s) across %d symbol(s)",
            len(bars),
            len({bar.symbol for bar in bars}),
        )
    else:
        await db.upsert_crypto_price_bars([bar.as_record() for bar in bars])

    for bar in sorted(bars, key=lambda item: (item.symbol, item.time)):
        state = app_state.binance_symbols.setdefault(
            bar.symbol,
            BinanceSymbolState(
                symbol=bar.symbol,
                asset=bar.asset,
                quote_asset=bar.quote_asset,
            ),
        )
        if state.last_bar_time is None or bar.time >= state.last_bar_time:
            state.last_bar_time = bar.time
            state.last_close = bar.close
            state.last_source = bar.source


async def _seed_binance_state_from_db(app_state: AppState) -> None:
    if CORE_DEBUG_MODE:
        return

    for symbol in BINANCE_TRACKED_SYMBOLS:
        latest = await db.get_latest_crypto_bar(symbol)
        if latest is None:
            continue
        state = app_state.binance_symbols[symbol]
        state.last_bar_time = latest["time"]
        state.last_close = float(latest["close"])
        state.last_source = latest["source"]


def _format_binance_status(app_state: AppState, now: datetime) -> str:
    latest_received_age = "n/a"
    if app_state.binance_last_message_at is not None:
        latest_received_age = str(
            int((now - app_state.binance_last_message_at).total_seconds())
        )

    latest_written = ",".join(
        f"{symbol}:{state.last_bar_time.strftime('%H:%M:%S') if state.last_bar_time else 'n/a'}"
        for symbol, state in sorted(app_state.binance_symbols.items())
    )
    return (
        f"symbols={','.join(BINANCE_TRACKED_SYMBOLS)} "
        f"connected={app_state.binance_ws_connected} "
        f"connections={app_state.binance_connection_count} "
        f"reconnects={app_state.binance_reconnect_count} "
        f"messages={app_state.binance_message_count} "
        f"last_recv_age={latest_received_age}s "
        f"latest_written={latest_written}"
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


async def _backfill_binance_window(
    app_state: AppState,
    http_client: httpx.AsyncClient,
) -> None:
    if BINANCE_BACKFILL_LOOKBACK_SECONDS <= 0:
        return

    end_time = current_bar_open_time() - timedelta(seconds=1)
    start_time = end_time - timedelta(seconds=BINANCE_BACKFILL_LOOKBACK_SECONDS - 1)
    request_start = start_time - timedelta(seconds=1)

    for symbol in BINANCE_TRACKED_SYMBOLS:
        state = app_state.binance_symbols[symbol]
        try:
            backfill_bars = await fetch_rest_klines(
                http_client,
                symbol=symbol,
                start_time=request_start,
                end_time=end_time,
            )
        except Exception as exc:
            logger.error("Binance backfill error for %s: %s", symbol, exc)
            continue

        filled = fill_missing_bars(
            symbol,
            backfill_bars,
            start_time=start_time,
            end_time=end_time,
            seed_close=state.last_close,
        )
        if filled:
            await _upsert_crypto_bars(app_state, filled)


async def _write_synthetic_binance_bars(
    app_state: AppState,
    *,
    upto_time: datetime | None = None,
) -> None:
    target_time = upto_time or current_bar_open_time()
    synthetic_bars: list[CryptoPriceBar] = []

    for symbol, state in app_state.binance_symbols.items():
        if state.last_close is None:
            continue

        start_time = state.last_bar_time + timedelta(seconds=1) if state.last_bar_time else target_time
        if start_time > target_time:
            continue

        synthetic_bars.extend(
            fill_missing_bars(
                symbol,
                [],
                start_time=start_time,
                end_time=target_time,
                seed_close=state.last_close,
            )
        )

    if synthetic_bars:
        await _upsert_crypto_bars(app_state, synthetic_bars)


async def _ingest_closed_binance_bar(
    app_state: AppState,
    bar: CryptoPriceBar,
) -> None:
    state = app_state.binance_symbols[bar.symbol]
    bars_to_write: list[CryptoPriceBar] = []

    if state.last_bar_time is not None and state.last_close is not None:
        gap_start = state.last_bar_time + timedelta(seconds=1)
        gap_end = bar.time - timedelta(seconds=1)
        if gap_start <= gap_end:
            bars_to_write.extend(
                fill_missing_bars(
                    bar.symbol,
                    [],
                    start_time=gap_start,
                    end_time=gap_end,
                    seed_close=state.last_close,
                )
            )

    bars_to_write.append(bar)
    await _upsert_crypto_bars(app_state, bars_to_write)


async def binance_collector_loop(
    app_state: AppState,
    http_client: httpx.AsyncClient,
) -> None:
    tracked_symbols = set(BINANCE_TRACKED_SYMBOLS)
    reconnect_delay = 1.0

    await _seed_binance_state_from_db(app_state)

    while not app_state.shutdown_event.is_set():
        try:
            await _backfill_binance_window(app_state, http_client)
            await _write_synthetic_binance_bars(app_state)
        except Exception as exc:
            logger.error("Binance sync preflight error: %s", exc)

        if app_state.shutdown_event.is_set():
            break

        stream_url = build_combined_kline_stream_url(BINANCE_TRACKED_SYMBOLS)

        try:
            async with websockets.connect(stream_url, close_timeout=10) as ws:
                app_state.binance_ws_connected = True
                app_state.binance_connection_count += 1
                if app_state.binance_connection_count > 1:
                    app_state.binance_reconnect_count += 1
                reconnect_delay = 1.0
                logger.info(
                    "Binance connected: subscribed to %s",
                    ",".join(BINANCE_TRACKED_SYMBOLS),
                )

                while not app_state.shutdown_event.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        await _write_synthetic_binance_bars(app_state)
                        continue

                    if raw in {"PING", "PONG"} or not raw:
                        continue

                    try:
                        message = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    bar = parse_ws_kline_message(
                        message,
                        tracked_symbols=tracked_symbols,
                    )
                    if bar is not None:
                        app_state.binance_message_count += 1
                        app_state.binance_last_message_at = datetime.now(timezone.utc)
                        await _ingest_closed_binance_bar(app_state, bar)

                    await _write_synthetic_binance_bars(app_state)
        except ConnectionClosed as exc:
            logger.warning(
                "Binance websocket disconnected (code=%s) - reconnecting",
                exc.code,
            )
        except Exception as exc:
            logger.error("Binance websocket error: %s", exc)
        finally:
            app_state.binance_ws_connected = False

        if app_state.shutdown_event.is_set():
            break

        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 30.0)


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
                "Heartbeat - tracking %d market(s), live %d, ws_connected=%s, ws_connections=%d, ws_messages=%d, last_ws_update_age=%ss | binance %s",
                tracked_count,
                live_count,
                app_state.ws_connected,
                app_state.ws_connection_count,
                app_state.ws_message_count,
                "n/a" if ws_age is None else ws_age,
                _format_binance_status(app_state, now),
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

    async with httpx.AsyncClient() as http_client, get_async_http_client() as binance_http_client:
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
            asyncio.create_task(
                binance_collector_loop(app_state, binance_http_client),
                name="binance-collector",
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
