"""One-shot wallet cleanup for contaminated Polymarket positions.

This command is intentionally conservative:
- redeem any condition that the public API marks as redeemable
- sell unresolved weather legs only when the current best bid can absorb the full size
- report anything else as still blocking the guarded weather bot
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from py_clob_client.clob_types import OrderArgs, OrderType, PartialCreateOrderOptions
from py_clob_client.order_builder.constants import SELL

from analysis.wallet_forensics.fetchers import WalletForensicsClient
from trading import config as trading_config
from trading.redeemer import is_neg_risk_market
from trading_weather.main import _best_book_price, _build_clob_client
from trading_weather.safe_ops import redeem_position
from trading_weather.wallet_guard import classify_market_bucket


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Perform live cleanup actions")
    parser.add_argument(
        "--include-weather-sells",
        action="store_true",
        help="Attempt full-size market exits for unresolved weather positions with enough bid depth",
    )
    return parser


@dataclass(slots=True)
class ConditionSnapshot:
    bucket: str
    condition_id: str
    title: str
    slug: str
    redeemable: bool
    yes_shares: Decimal
    no_shares: Decimal
    token_id: str | None
    top_bid_price: float | None = None
    top_bid_size: float | None = None
    current_side: str | None = None
    current_shares: Decimal = Decimal("0")


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _outcome_side(row: dict[str, Any]) -> str | None:
    outcome = str(row.get("outcome") or "").strip().lower()
    if outcome in {"yes", "up"}:
        return "yes"
    if outcome in {"no", "down"}:
        return "no"
    return None


def _title(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("question") or "").strip()


def _slug(row: dict[str, Any]) -> str:
    return str(row.get("slug") or "").strip()


def aggregate_condition_snapshots(rows: list[dict[str, Any]]) -> list[ConditionSnapshot]:
    grouped: dict[str, ConditionSnapshot] = {}
    for row in rows:
        condition_id = str(row.get("conditionId") or "").strip()
        if not condition_id:
            continue
        snapshot = grouped.get(condition_id)
        if snapshot is None:
            snapshot = ConditionSnapshot(
                bucket=classify_market_bucket(row),
                condition_id=condition_id,
                title=_title(row),
                slug=_slug(row),
                redeemable=bool(row.get("redeemable")),
                yes_shares=Decimal("0"),
                no_shares=Decimal("0"),
                token_id=None,
            )
            grouped[condition_id] = snapshot
        snapshot.redeemable = snapshot.redeemable or bool(row.get("redeemable"))
        side = _outcome_side(row)
        size = _as_decimal(row.get("size"))
        token_id = str(row.get("asset") or row.get("asset_id") or "").strip() or None
        if side == "yes":
            snapshot.yes_shares += size
            snapshot.current_side = "yes"
            snapshot.current_shares = size
            snapshot.token_id = token_id
        elif side == "no":
            snapshot.no_shares += size
            snapshot.current_side = "no"
            snapshot.current_shares = size
            snapshot.token_id = token_id
    return list(grouped.values())


def enrich_weather_liquidity(snapshots: list[ConditionSnapshot]) -> None:
    clob = _build_clob_client()
    for snapshot in snapshots:
        if snapshot.bucket != "weather" or snapshot.redeemable or not snapshot.token_id:
            continue
        snapshot.top_bid_price = _best_book_price(clob, snapshot.token_id, side="SELL")
        try:
            book = clob.get_order_book(snapshot.token_id)
        except Exception:
            snapshot.top_bid_size = None
            continue
        bids = book.bids if hasattr(book, "bids") else []
        if not bids:
            snapshot.top_bid_size = None
            continue
        best_price = max(float(item.price) for item in bids)
        snapshot.top_bid_size = sum(float(item.size) for item in bids if float(item.price) >= best_price - 1e-12)


def assess_snapshot(snapshot: ConditionSnapshot) -> tuple[str, str]:
    if snapshot.redeemable:
        return "redeem_now", "public_api_redeemable"
    if snapshot.bucket != "weather":
        return "manual_blocked", "non_weather_not_redeemable"
    if not snapshot.token_id:
        return "manual_blocked", "missing_token_id"
    bid = snapshot.top_bid_price
    depth = snapshot.top_bid_size
    shares = float(snapshot.current_shares)
    if bid is None or bid <= 0:
        return "manual_blocked", "no_live_bid"
    if depth is None or depth + 1e-9 < shares:
        return "manual_blocked", "insufficient_bid_depth"
    return "sell_now", "full_size_bid_available"


async def _sell_exact_position(
    snapshot: ConditionSnapshot,
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    if not snapshot.token_id or snapshot.top_bid_price is None:
        raise RuntimeError("Missing token or bid for cleanup sell")
    clob = _build_clob_client()
    size = round(float(snapshot.current_shares), 6)
    order_args = OrderArgs(
        token_id=snapshot.token_id,
        price=round(float(snapshot.top_bid_price), 3),
        size=size,
        side=SELL,
    )
    signed = clob.create_order(
        order_args,
        PartialCreateOrderOptions(tick_size="0.001", neg_risk=False),
    )
    response = clob.post_order(signed, OrderType.GTC)
    status = str(response.get("status") or "").upper() if isinstance(response, dict) else ""
    order_id = response.get("orderID") or response.get("id") if isinstance(response, dict) else None
    if status in {"MATCHED", "FILLED"}:
        return {
            "status": "filled",
            "order_id": order_id,
            "fill_price": float(response.get("average_price") or response.get("price") or snapshot.top_bid_price),
            "fill_shares": float(response.get("size_matched") or response.get("matched_size") or response.get("filled") or size),
        }
    if not order_id:
        raise RuntimeError(f"Cleanup sell returned no order id: {response!r}")

    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        order = clob.get_order(order_id)
        order_status = str(order.get("status") or "").upper() if isinstance(order, dict) else ""
        if order_status in {"MATCHED", "FILLED"}:
            return {
                "status": "filled",
                "order_id": order_id,
                "fill_price": float(order.get("average_price") or order.get("price") or snapshot.top_bid_price),
                "fill_shares": float(order.get("size_matched") or order.get("matched_size") or order.get("filled") or size),
            }
        if order_status in {"CANCELLED", "EXPIRED"}:
            break
        await asyncio.sleep(0.25)

    clob.cancel(order_id)
    raise RuntimeError(f"Cleanup sell did not fill in time: {order_id}")


async def run_cleanup(*, execute: bool, include_weather_sells: bool) -> int:
    client = WalletForensicsClient()
    try:
        rows = client.fetch_positions(trading_config.PROXY_WALLET, closed=False)
        snapshots = aggregate_condition_snapshots(rows)
        enrich_weather_liquidity(snapshots)

        print(f"Wallet: {trading_config.PROXY_WALLET}")
        print(f"Open public positions: {len(rows)}")

        actions: list[tuple[ConditionSnapshot, str, str]] = []
        for snapshot in snapshots:
            action, reason = assess_snapshot(snapshot)
            if action == "sell_now" and not include_weather_sells:
                action, reason = "manual_blocked", "weather_sell_disabled"
            actions.append((snapshot, action, reason))
            print(
                f"{action:14s} | {snapshot.bucket:13s} | {snapshot.title} | "
                f"yes={snapshot.yes_shares} no={snapshot.no_shares} | reason={reason}"
            )

        if not execute:
            print("Dry-run only. Re-run with --execute to send cleanup transactions/orders.")
            return 0

        action_priority = {"redeem_now": 0, "sell_now": 1, "manual_blocked": 2}
        for snapshot, action, reason in sorted(actions, key=lambda item: action_priority.get(item[1], 99)):
            print(f"EXECUTE {action} | {snapshot.title} | reason={reason}")
            try:
                if action == "redeem_now":
                    neg_risk = await is_neg_risk_market(snapshot.condition_id)
                    result = redeem_position(
                        snapshot.condition_id,
                        neg_risk=neg_risk,
                        yes_shares=float(snapshot.yes_shares),
                        no_shares=float(snapshot.no_shares),
                    )
                    print(
                        f"  redeemed | mode={result.mode} tx={result.transaction_hash} state={result.state or ''}"
                    )
                elif action == "sell_now":
                    result = await _sell_exact_position(snapshot)
                    print(
                        f"  sold | order={result.get('order_id')} shares={result.get('fill_shares')} "
                        f"price={result.get('fill_price')}"
                    )
                else:
                    print("  skipped")
            except Exception as exc:
                print(f"  failed | {type(exc).__name__}: {exc}")

        remaining = client.fetch_positions(trading_config.PROXY_WALLET, closed=False)
        print(f"Remaining open public positions: {len(remaining)}")
        for row in remaining:
            print(
                f"  {classify_market_bucket(row):13s} | {str(row.get('title') or row.get('question') or '').strip()} | "
                f"outcome={row.get('outcome')} size={row.get('size')} redeemable={row.get('redeemable')}"
            )
        return 0
    finally:
        client.close()


def main() -> int:
    args = build_arg_parser().parse_args()
    return asyncio.run(
        run_cleanup(
            execute=bool(args.execute),
            include_weather_sells=bool(args.include_weather_sells),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
