"""Wallet activity tracker service — periodically fetches on-chain activity for tracked profiles."""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from shared.db import close_pool, init_pool
from shared.http import get_async_http_client
from shared.logging import setup_logger
from wallet_tracker.config import (
    WALLET_TRACKER_INTERVAL_SECONDS,
    WALLET_TRACKER_PROFILE,
    WALLET_TRACKER_TIMEOUT_SECONDS,
)
from wallet_tracker.db import (
    create_wallet_tracker_tables,
    get_watermark,
    insert_activity_rows,
    update_watermark,
)
from wallet_tracker.fetcher import fetch_activity, resolve_wallet

logger = setup_logger("wallet_tracker")


@dataclass
class AppState:
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    proxy_wallet: str | None = None
    profile_name: str = WALLET_TRACKER_PROFILE


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, app_state: AppState) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, app_state.shutdown_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: loop.call_soon_threadsafe(app_state.shutdown_event.set))


async def tracker_loop(app_state: AppState, http_client: httpx.AsyncClient) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            if app_state.proxy_wallet is None:
                profile = await resolve_wallet(http_client, app_state.profile_name)
                app_state.proxy_wallet = profile.get("proxyWallet") or profile.get("address", "")
                logger.info(
                    "Resolved %s -> %s",
                    app_state.profile_name,
                    app_state.proxy_wallet[:16] + "...",
                )

            last_ts = await get_watermark(app_state.profile_name)
            now_ts = int(datetime.now(UTC).timestamp())
            start_ts = (last_ts + 1) if last_ts is not None else None

            rows = await fetch_activity(
                http_client,
                app_state.proxy_wallet,
                start_ts=start_ts,
                end_ts=now_ts,
            )

            if rows:
                inserted = await insert_activity_rows(
                    rows,
                    profile_name=app_state.profile_name,
                    proxy_wallet=app_state.proxy_wallet,
                )
                max_ts = max(int(row.get("timestamp") or 0) for row in rows)
                if max_ts > 0:
                    await update_watermark(app_state.profile_name, app_state.proxy_wallet, max_ts)

                logger.info(
                    "Fetched %d row(s), inserted %d new for %s (watermark: %s -> %s)",
                    len(rows),
                    inserted,
                    app_state.profile_name,
                    last_ts,
                    max_ts,
                )
            else:
                logger.info("No new activity for %s", app_state.profile_name)

        except Exception:
            logger.exception("Wallet tracker loop failed")

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(),
                timeout=WALLET_TRACKER_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            pass


async def main() -> None:
    logger.info(
        "Wallet tracker starting (profile=%s, interval=%ds)...",
        WALLET_TRACKER_PROFILE,
        WALLET_TRACKER_INTERVAL_SECONDS,
    )
    await init_pool()
    await create_wallet_tracker_tables()

    app_state = AppState()
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, app_state)

    async with get_async_http_client(timeout=float(WALLET_TRACKER_TIMEOUT_SECONDS)) as http_client:
        tasks = [
            asyncio.create_task(tracker_loop(app_state, http_client), name="wallet-tracker"),
        ]

        await app_state.shutdown_event.wait()
        logger.info("Wallet tracker shutting down...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
