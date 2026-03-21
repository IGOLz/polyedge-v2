from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    ApiCreds,
    AssetType,
    BalanceAllowanceParams,
    MarketOrderArgs,
    OrderType,
)

from shared.api import fetch_market_resolution, fetch_open_btc_5min_markets
from shared.models import MarketState
from trading import config
from trading.redeemer import is_neg_risk_market, redeem_condition
from trading.relayer import PolymarketRelayerClient

LAST_STUCK_BTC_5M_CASE: dict[str, Any] = {
    "case_name": "btc-5m-stuck-20260321-1455utc",
    "market_id": "0xbcb0ccec0b3eaad3f88926b8de345c998df35af5f6b2e0bdcac7dcfae4975bc9",
    "market_type": "BTC_5m",
    "started_at": "2026-03-21T14:55:00+00:00",
    "ended_at": "2026-03-21T15:00:00+00:00",
    "up_token_id": "45072370415483832048641487795749685291015579615663212094712611541254426787525",
    "down_token_id": "20518276487878124204878476039828122298027820785394293171120616712430967289612",
    "expected_winner": "Down",
    "original_trade_context": {
        "up_order_id": "0xe3170ead8a43cd4cddc3ca77f711982c8d5777d3704c6e2665ddea334ee0ac30",
        "down_order_id": "0xc2df5bf305e800ce09ba537129aae20fb407090ed22dc4ebffad6b391c1059e8",
        "up_fill_price": 0.06,
        "up_fill_size": 16.666665,
        "down_fill_price": 0.95,
        "down_fill_size": 1.05263,
    },
}


def configure_logging() -> tuple[logging.Logger, Path]:
    log_dir = REPO_ROOT / "data" / "redeem_debug"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"btc_5m_dual_bet_{datetime.now():%Y%m%d_%H%M%S}.log"

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    for name in ("polyedge.trading", "polyedge.trading.debug"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.DEBUG)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    logger = logging.getLogger("btc_redeem_smoke")
    logger.setLevel(logging.DEBUG)
    logger.info("Log file: %s", log_path)
    return logger, log_path


def json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, default=str)


def build_clob_client() -> ClobClient:
    creds = ApiCreds(
        api_key=config.API_KEY,
        api_secret=config.API_SECRET,
        api_passphrase=config.API_PASSPHRASE,
    )
    return ClobClient(
        config.CLOB_BASE_URL,
        key=config.PRIVATE_KEY,
        chain_id=config.CHAIN_ID,
        creds=creds,
        signature_type=2,
        funder=config.PROXY_WALLET,
    )


def parse_iso8601_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_market_from_case(case_data: dict[str, Any]) -> MarketState:
    return MarketState(
        market_id=str(case_data["market_id"]),
        up_token_id=str(case_data["up_token_id"]),
        down_token_id=str(case_data["down_token_id"]),
        started_at=parse_iso8601_utc(str(case_data["started_at"])),
        ended_at=parse_iso8601_utc(str(case_data["ended_at"])),
        market_type=str(case_data.get("market_type") or "BTC_5m"),
    )


async def fetch_market_debug_snapshot(market_id: str) -> dict[str, Any]:
    async with config.get_http_client(timeout=20.0) as client:
        response = await client.get(f"{config.CLOB_BASE_URL}/markets/{market_id}", timeout=20)
        response.raise_for_status()
        return response.json()


def get_collateral_balance_info(clob: ClobClient) -> dict[str, Any]:
    return clob.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
    )


def get_token_balance_info(clob: ClobClient, token_id: str) -> dict[str, Any]:
    return clob.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
    )


def get_book_snapshot(clob: ClobClient, token_id: str) -> dict[str, Any]:
    book = clob.get_order_book(token_id)
    asks = []
    bids = []

    for level in list(getattr(book, "asks", []) or [])[:5]:
        asks.append({"price": float(level.price), "size": float(level.size)})
    for level in list(getattr(book, "bids", []) or [])[:5]:
        bids.append({"price": float(level.price), "size": float(level.size)})

    return {"token_id": token_id, "asks": asks, "bids": bids}


def wait_for_order_terminal_state(
    clob: ClobClient,
    order_id: str,
    logger: logging.Logger,
    *,
    timeout_seconds: float = 20.0,
    poll_interval_seconds: float = 0.5,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_order: dict[str, Any] | None = None
    while time.time() < deadline:
        order = clob.get_order(order_id)
        if isinstance(order, dict):
            last_order = order
            status = str(order.get("status") or "").upper()
            logger.info("Order %s status=%s payload=%s", order_id, status or "?", json_dump(order))
            if status in {"MATCHED", "FILLED", "CANCELLED", "EXPIRED"}:
                return order
        time.sleep(poll_interval_seconds)
    raise TimeoutError(
        f"Order {order_id} did not reach a terminal state within {timeout_seconds:.1f}s. "
        f"Last payload: {last_order!r}"
    )


def place_market_buy(
    clob: ClobClient,
    *,
    token_id: str,
    amount_usd: float,
    label: str,
    logger: logging.Logger,
) -> dict[str, Any]:
    logger.info("Preparing %s market buy for $%.2f on token=%s", label, amount_usd, token_id)
    logger.info("%s orderbook snapshot before order: %s", label, json_dump(get_book_snapshot(clob, token_id)))

    order_args = MarketOrderArgs(
        token_id=token_id,
        amount=amount_usd,
        side="BUY",
        order_type=OrderType.FOK,
    )
    logger.info("%s market order args: %s", label, order_args)

    signed_order = clob.create_market_order(order_args)
    logger.info("%s signed market order built successfully", label)

    response = clob.post_order(signed_order, OrderType.FOK)
    logger.info("%s raw post_order response: %s", label, json_dump(response))

    if not isinstance(response, dict):
        raise RuntimeError(f"{label} unexpected order response type: {type(response)}")

    order_id = str(response.get("orderID") or response.get("order_id") or "").strip()
    if order_id:
        final_order = wait_for_order_terminal_state(clob, order_id, logger)
    else:
        final_order = response

    status = str(final_order.get("status") or "").upper()
    if status not in {"MATCHED", "FILLED"}:
        raise RuntimeError(f"{label} order was not filled. Final payload: {final_order!r}")

    fill_price = float(final_order.get("average_price") or final_order.get("price") or 0.0)
    fill_size = float(
        final_order.get("size_matched")
        or final_order.get("matched_size")
        or final_order.get("filled")
        or 0.0
    )
    logger.info(
        "%s filled successfully at price=%.6f size=%.6f notional=%.6f",
        label,
        fill_price,
        fill_size,
        fill_price * fill_size,
    )
    return {
        "label": label,
        "order_id": order_id,
        "fill_price": fill_price,
        "fill_size": fill_size,
        "raw_response": response,
        "final_order": final_order,
    }


def choose_market(markets: list[MarketState], logger: logging.Logger, override_market_id: str = "") -> MarketState:
    if not markets:
        raise RuntimeError("No open BTC 5-minute markets were returned by discovery")

    logger.info("Discovered %d BTC 5m market(s)", len(markets))
    for market in markets:
        logger.info(
            "Market candidate id=%s type=%s start=%s end=%s up=%s down=%s",
            market.market_id,
            market.market_type,
            market.started_at.isoformat(),
            market.ended_at.isoformat(),
            market.up_token_id,
            market.down_token_id,
        )

    if override_market_id:
        for market in markets:
            if market.market_id == override_market_id:
                logger.info("Using market override: %s", override_market_id)
                return market
        raise RuntimeError(f"Override market_id {override_market_id} was not found among open BTC 5m markets")

    now = datetime.now(timezone.utc)
    active_now = sorted(
        [m for m in markets if m.started_at <= now < m.ended_at],
        key=lambda m: m.ended_at,
    )
    if active_now:
        chosen = active_now[0]
        logger.info("Selected currently active market ending soonest: %s", chosen.market_id)
        return chosen

    chosen = sorted(markets, key=lambda m: m.started_at)[0]
    logger.info("No active market yet. Selected next upcoming market: %s", chosen.market_id)
    return chosen


async def wait_until_market_window(
    market: MarketState,
    logger: logging.Logger,
    *,
    poll_seconds: int,
) -> None:
    while True:
        now = datetime.now(timezone.utc)
        if now >= market.started_at:
            logger.info("Market %s is live. now=%s", market.market_id, now.isoformat())
            return
        remaining = (market.started_at - now).total_seconds()
        logger.info(
            "Waiting %.1fs for market %s to start at %s",
            remaining,
            market.market_id,
            market.started_at.isoformat(),
        )
        await asyncio.sleep(min(poll_seconds, max(1, int(remaining))))


async def wait_for_resolution(
    market: MarketState,
    logger: logging.Logger,
    *,
    poll_seconds: int,
    max_minutes: int,
) -> dict[str, Any]:
    max_deadline = market.ended_at.timestamp() + (max_minutes * 60)

    while True:
        now = datetime.now(timezone.utc)
        if now.timestamp() > max_deadline:
            raise TimeoutError(
                f"Market {market.market_id} was not resolved within {max_minutes} minutes of its end time"
            )

        if now < market.ended_at:
            remaining = (market.ended_at - now).total_seconds()
            logger.info(
                "Market still open. Waiting %.1fs until end time %s",
                remaining,
                market.ended_at.isoformat(),
            )
            await asyncio.sleep(min(poll_seconds, max(1, int(remaining))))
            continue

        async with config.get_http_client(timeout=20.0) as client:
            resolution = await fetch_market_resolution(client, market.market_id)

        logger.info("Resolution poll payload: %s", json_dump(resolution))
        if resolution:
            return resolution

        logger.info("Market ended but not resolved yet. Sleeping %ss", poll_seconds)
        await asyncio.sleep(poll_seconds)


def log_balance_snapshot(clob: ClobClient, market: MarketState, logger: logging.Logger, label: str) -> None:
    collateral = get_collateral_balance_info(clob)
    up_balance = get_token_balance_info(clob, market.up_token_id)
    down_balance = get_token_balance_info(clob, market.down_token_id)
    logger.info(
        "%s collateral balance snapshot: %s",
        label,
        json_dump(collateral),
    )
    logger.info("%s UP token balance snapshot: %s", label, json_dump(up_balance))
    logger.info("%s DOWN token balance snapshot: %s", label, json_dump(down_balance))


async def async_main(args: argparse.Namespace) -> int:
    logger, log_path = configure_logging()
    logger.info("Repo root: %s", REPO_ROOT)
    logger.info("Python executable: %s", sys.executable)
    logger.info("CWD: %s", Path.cwd())

    logger.info(
        "Config summary: eoa=%s proxy=%s relayer_key_present=%s relayer_key_address=%s relayer_url=%s",
        config.EOA_ADDRESS,
        config.PROXY_WALLET,
        bool(config.RELAYER_API_KEY),
        config.RELAYER_API_KEY_ADDRESS,
        config.RELAYER_BASE_URL,
    )

    relayer = PolymarketRelayerClient()
    api_keys = relayer.get_api_keys()
    logger.info("Relayer auth validated. visible_keys=%d payload=%s", len(api_keys), json_dump(api_keys))
    logger.info(
        "Relayer signer=%s derived_proxy=%s configured_proxy=%s",
        relayer.signer_address,
        relayer.derived_proxy_wallet,
        relayer.proxy_wallet,
    )

    clob = build_clob_client()
    logger.info("CLOB client created successfully")

    case_data: dict[str, Any] | None = None
    expected_winner = ""
    if args.resume_last_stuck_market:
        case_data = dict(LAST_STUCK_BTC_5M_CASE)
        market = build_market_from_case(case_data)
        expected_winner = str(case_data.get("expected_winner") or "").strip()
        logger.info("Run mode: redeem-only resume mode for embedded stuck BTC 5m case")
        logger.info("Embedded case payload: %s", json_dump(case_data))
    else:
        logger.info("Run mode: live dual-bet smoke test")
        async with config.get_http_client(timeout=20.0) as client:
            market = choose_market(
                await fetch_open_btc_5min_markets(client),
                logger,
                override_market_id=args.market_id,
            )
        await wait_until_market_window(market, logger, poll_seconds=args.poll_seconds)

        log_balance_snapshot(clob, market, logger, "PRE-TRADE")

        up_fill = place_market_buy(
            clob,
            token_id=market.up_token_id,
            amount_usd=args.bet_usd,
            label="UP",
            logger=logger,
        )
        down_fill = place_market_buy(
            clob,
            token_id=market.down_token_id,
            amount_usd=args.bet_usd,
            label="DOWN",
            logger=logger,
        )

        logger.info("UP fill summary: %s", json_dump(up_fill))
        logger.info("DOWN fill summary: %s", json_dump(down_fill))
        log_balance_snapshot(clob, market, logger, "POST-TRADE")

    market_snapshot = await fetch_market_debug_snapshot(market.market_id)
    logger.info("Raw market snapshot before resolution/redeem: %s", json_dump(market_snapshot))

    resolution = await wait_for_resolution(
        market,
        logger,
        poll_seconds=args.poll_seconds,
        max_minutes=args.max_resolution_minutes,
    )
    logger.info("Final resolution payload: %s", json_dump(resolution))
    if expected_winner:
        logger.info("Expected winner for this run: %s", expected_winner)
        if resolution.get("winner") != expected_winner:
            raise RuntimeError(
                f"Resolution mismatch for {market.market_id}: expected {expected_winner}, got {resolution.get('winner')}"
            )
        logger.info("Resolution matched expected winner for embedded case")

    neg_risk = await is_neg_risk_market(market.market_id)
    logger.info("Neg-risk lookup for %s => %s", market.market_id, neg_risk)
    log_balance_snapshot(clob, market, logger, "PRE-REDEEM")

    redemption = await redeem_condition(
        market.market_id,
        neg_risk,
        metadata=(
            f"BTC 5m resume redeem {market.market_id}"
            if args.resume_last_stuck_market
            else f"BTC 5m dual-bet smoke test {market.market_id}"
        ),
    )
    logger.info(
        "Redemption result: mode=%s transaction_id=%s state=%s tx_hash=%s",
        redemption.mode,
        redemption.transaction_id,
        redemption.state,
        redemption.transaction_hash,
    )

    log_balance_snapshot(clob, market, logger, "POST-REDEEM")
    if case_data:
        logger.info("Embedded case original trade context: %s", json_dump(case_data.get("original_trade_context")))
    logger.info("Smoke test completed successfully. Log file: %s", log_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Buy $1 UP and $1 DOWN on a BTC 5m market and redeem after resolution, "
            "or resume a known stuck market in redeem-only mode."
        )
    )
    parser.add_argument(
        "--bet-usd",
        type=float,
        default=1.0,
        help="Dollar amount to buy on each side (default: 1.0)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=15,
        help="Polling interval for start / resolution / status checks (default: 15)",
    )
    parser.add_argument(
        "--max-resolution-minutes",
        type=int,
        default=90,
        help="Maximum minutes to wait after market end for resolution (default: 90)",
    )
    parser.add_argument(
        "--market-id",
        default="",
        help="Optional BTC 5m conditionId override to target a specific open market",
    )
    parser.add_argument(
        "--resume-last-stuck-market",
        action="store_true",
        help=(
            "Redeem-only mode for the known 2026-03-21 BTC 5m market from the previous stuck run. "
            "Skips placing new bets, verifies winner=Down, and then attempts redemption."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        logging.getLogger("btc_redeem_smoke").warning("Interrupted by user")
        return 130
    except Exception as exc:
        logging.getLogger("btc_redeem_smoke").exception("Smoke test failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
