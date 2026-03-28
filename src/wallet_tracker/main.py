"""Wallet activity tracker service for Polymarket public profiles."""

from __future__ import annotations

import argparse
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wallet activity tracker")
    parser.add_argument("--profile", type=str, default=WALLET_TRACKER_PROFILE, help="Public Polymarket profile name")
    parser.add_argument("--wallet", type=str, default=None, help="Explicit proxy wallet override")
    parser.add_argument("--once", action="store_true", help="Fetch a single historical window and exit")
    parser.add_argument("--start-iso", type=str, default=None, help="Explicit UTC start timestamp (ISO 8601)")
    parser.add_argument("--end-iso", type=str, default=None, help="Explicit UTC end timestamp (ISO 8601)")
    parser.add_argument(
        "--ignore-watermark",
        action="store_true",
        help="Ignore the stored watermark and use the explicit start timestamp as-is",
    )
    parser.add_argument(
        "--skip-watermark-update",
        action="store_true",
        help="Do not advance the stored watermark after the fetch",
    )
    return parser


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, app_state: AppState) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, app_state.shutdown_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: loop.call_soon_threadsafe(app_state.shutdown_event.set))


def _parse_iso_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return int(parsed.timestamp())


async def _ensure_proxy_wallet(
    app_state: AppState,
    http_client: httpx.AsyncClient,
    explicit_wallet: str | None = None,
) -> str:
    if explicit_wallet:
        app_state.proxy_wallet = explicit_wallet.strip().lower()
        return app_state.proxy_wallet
    if app_state.proxy_wallet is None:
        profile = await resolve_wallet(http_client, app_state.profile_name)
        app_state.proxy_wallet = profile.get("proxyWallet") or profile.get("address", "")
        logger.info(
            "Resolved %s -> %s",
            app_state.profile_name,
            app_state.proxy_wallet[:16] + "...",
        )
    return app_state.proxy_wallet


async def fetch_and_persist_window(
    app_state: AppState,
    http_client: httpx.AsyncClient,
    *,
    explicit_wallet: str | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
    ignore_watermark: bool = False,
    update_watermark_enabled: bool = True,
) -> dict[str, int | None]:
    proxy_wallet = await _ensure_proxy_wallet(app_state, http_client, explicit_wallet)
    last_ts = None if ignore_watermark else await get_watermark(app_state.profile_name)
    effective_start = start_ts
    if not ignore_watermark and last_ts is not None:
        effective_start = max(int(start_ts), last_ts + 1) if start_ts is not None else (last_ts + 1)
    effective_end = end_ts if end_ts is not None else int(datetime.now(UTC).timestamp())

    rows = await fetch_activity(
        http_client,
        proxy_wallet,
        start_ts=effective_start,
        end_ts=effective_end,
    )

    inserted = 0
    max_ts = last_ts
    if rows:
        inserted = await insert_activity_rows(
            rows,
            profile_name=app_state.profile_name,
            proxy_wallet=proxy_wallet,
        )
        max_ts = max(int(row.get("timestamp") or 0) for row in rows)
        if update_watermark_enabled and max_ts and (last_ts is None or max_ts > last_ts):
            await update_watermark(app_state.profile_name, proxy_wallet, max_ts)

    logger.info(
        "Fetched %d row(s), inserted %d new for %s (window: %s -> %s, watermark: %s -> %s)",
        len(rows),
        inserted,
        app_state.profile_name,
        effective_start,
        effective_end,
        last_ts,
        max_ts,
    )
    return {
        "start_ts": effective_start,
        "end_ts": effective_end,
        "last_ts": last_ts,
        "max_ts": max_ts,
        "fetched_count": len(rows),
        "inserted_count": inserted,
    }


async def tracker_loop(app_state: AppState, http_client: httpx.AsyncClient) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            await fetch_and_persist_window(app_state, http_client)
        except Exception:
            logger.exception("Wallet tracker loop failed")

        try:
            await asyncio.wait_for(
                app_state.shutdown_event.wait(),
                timeout=WALLET_TRACKER_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            pass


async def async_main(args: argparse.Namespace) -> None:
    logger.info(
        "Wallet tracker starting (profile=%s, interval=%ds)...",
        args.profile,
        WALLET_TRACKER_INTERVAL_SECONDS,
    )
    await init_pool()
    await create_wallet_tracker_tables()

    app_state = AppState(profile_name=args.profile, proxy_wallet=args.wallet)
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, app_state)

    async with get_async_http_client(timeout=float(WALLET_TRACKER_TIMEOUT_SECONDS)) as http_client:
        if args.once:
            await fetch_and_persist_window(
                app_state,
                http_client,
                explicit_wallet=args.wallet,
                start_ts=_parse_iso_timestamp(args.start_iso),
                end_ts=_parse_iso_timestamp(args.end_iso),
                ignore_watermark=bool(args.ignore_watermark),
                update_watermark_enabled=not bool(args.skip_watermark_update),
            )
            await close_pool()
            return

        tasks = [
            asyncio.create_task(tracker_loop(app_state, http_client), name="wallet-tracker"),
        ]

        await app_state.shutdown_event.wait()
        logger.info("Wallet tracker shutting down...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    await close_pool()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(async_main(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
