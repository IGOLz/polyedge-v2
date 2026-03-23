"""Dedicated live weather merge bot based on the ColdMath public strategy."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analysis.wallet_forensics.utils import safe_float
from shared.config import PROXY_URL
from shared.db import close_pool, create_weather_tables, init_pool
from trading import config as trading_config
from trading import db as trading_db
from trading.utils import log
from trading_weather import config
from trading_weather import db as weather_db
from trading_weather.safe_ops import ensure_weather_allowances, merge_position, redeem_position
from trading_weather.strategy import (
    build_runtime_config,
    compute_mergeable_shares,
    open_position_exposure,
    plan_entry,
    rank_live_candidates,
)
from weather.storage import fetch_active_weather_contexts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PolyEdge dedicated weather merge bot")
    parser.add_argument("--dry-run", action="store_true", help="Observe candidates without placing live orders")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument(
        "--config-path",
        type=str,
        default=str(config.DEFAULT_BOT_CONFIG_PATH),
        help="Path to wallet_inventory_rebalancing_merge_backtest_bot_config.json",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    return parser


def _build_clob_client():
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds

    creds = ApiCreds(
        api_key=trading_config.API_KEY,
        api_secret=trading_config.API_SECRET,
        api_passphrase=trading_config.API_PASSPHRASE,
    )
    return ClobClient(
        trading_config.CLOB_BASE_URL,
        key=trading_config.PRIVATE_KEY,
        chain_id=137,
        creds=creds,
        signature_type=2,
        funder=trading_config.PROXY_WALLET,
    )


def _parse_fill_from_resp(resp: dict | None, fallback_shares: int, fallback_price: float) -> tuple[int, float]:
    fill_shares = fallback_shares
    fill_price = fallback_price
    if isinstance(resp, dict):
        raw_shares = resp.get("size_matched") or resp.get("matched_size") or resp.get("filled")
        raw_price = resp.get("average_price") or resp.get("price")
        if raw_shares is not None:
            try:
                parsed_shares = math.floor(float(raw_shares))
            except (TypeError, ValueError):
                parsed_shares = 0
            if parsed_shares > 0:
                fill_shares = parsed_shares
        if raw_price is not None:
            try:
                parsed_price = float(raw_price)
            except (TypeError, ValueError):
                parsed_price = 0.0
            if parsed_price > 0:
                fill_price = parsed_price
    return fill_shares, fill_price


def _best_book_price(clob, token_id: str, *, side: str) -> float | None:
    try:
        book = clob.get_order_book(token_id)
    except Exception:
        return None

    if side == "SELL":
        bids = book.bids if hasattr(book, "bids") else []
        if not bids:
            return None
        return float(max(bids, key=lambda item: float(item.price)).price)

    asks = book.asks if hasattr(book, "asks") else []
    if not asks:
        return None
    return float(min(asks, key=lambda item: float(item.price)).price)


def _get_token_balance(clob, token_id: str) -> float:
    from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

    balance = clob.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
    )
    return int(balance.get("balance", "0")) / 1_000_000


def _get_usdc_balance(clob) -> float:
    from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

    balance = clob.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
    return int(balance.get("balance", "0")) / 1_000_000


def _place_fok_order(clob, token_id: str, *, price: float, shares: int, side: str) -> dict[str, Any] | None:
    from py_clob_client.clob_types import OrderArgs, OrderType

    if shares <= 0:
        return None
    order_args = OrderArgs(token_id=token_id, price=round(price, 2), size=float(shares), side=side)
    signed = clob.create_order(order_args)
    resp = clob.post_order(signed, OrderType.FOK)
    status = (resp.get("status") or "").upper() if isinstance(resp, dict) else ""
    if status in {"MATCHED", "FILLED"}:
        fill_shares, fill_price = _parse_fill_from_resp(resp, shares, price)
        return {
            "order_id": resp.get("orderID") or resp.get("id"),
            "fill_shares": fill_shares,
            "fill_price": fill_price,
            "raw": resp,
        }
    return None


def _load_bot_config(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def _log_event(log_type: str, message: str, data: dict[str, Any] | None = None) -> None:
    await trading_db.log_event(log_type, message, data, echo=False)
    log.info(message)


def _cycle_status_message(
    *,
    balance: float,
    active_positions: int,
    active_exposure_usd: float,
    context_count: int,
    market_count: int,
    candidate_count: int,
    entry_attempts: int,
    top_candidate: dict[str, Any] | None,
) -> str:
    message = (
        "[WEATHER-MERGE] Cycle OK | "
        f"balance={balance:.2f} "
        f"active_positions={active_positions} "
        f"exposure={active_exposure_usd:.2f} "
        f"contexts={context_count} "
        f"markets={market_count} "
        f"candidates={candidate_count} "
        f"entries={entry_attempts}"
    )
    if top_candidate:
        combined_cost = safe_float(top_candidate.get("combined_cost"))
        merge_edge = safe_float(top_candidate.get("merge_edge"))
        message += (
            " | top="
            f"{top_candidate.get('city')} {top_candidate.get('bucket_label')} "
            f"cost={(combined_cost if combined_cost is not None else float('nan')):.4f} "
            f"edge={(merge_edge if merge_edge is not None else float('nan')):.4f}"
        )
    else:
        message += " | stand_down=no_qualifying_candidate"
    return message


async def _handle_partial_unwind(clob, position: dict[str, Any]) -> None:
    yes_shares = safe_float(position.get("yes_shares")) or 0.0
    no_shares = safe_float(position.get("no_shares")) or 0.0
    side = "yes" if yes_shares > no_shares else "no"
    token_id = position["yes_token_id"] if side == "yes" else position["no_token_id"]
    shares = math.floor(abs(yes_shares - no_shares))
    if shares <= 0:
        return

    sell_price = _best_book_price(clob, token_id, side="SELL")
    if sell_price is None:
        await weather_db.update_weather_merge_status(
            position["id"],
            status="partial_orphaned",
            notes="Could not find sell liquidity for unmatched inventory",
        )
        return

    fill = await asyncio.to_thread(
        _place_fok_order,
        clob,
        token_id,
        price=sell_price,
        shares=shares,
        side="SELL",
    )
    if not fill:
        await weather_db.update_weather_merge_status(
            position["id"],
            status="partial_orphaned",
            notes="Unwind sell did not fill",
        )
        return

    remaining_yes = max(0.0, yes_shares - (fill["fill_shares"] if side == "yes" else 0.0))
    remaining_no = max(0.0, no_shares - (fill["fill_shares"] if side == "no" else 0.0))
    paired = compute_mergeable_shares(yes_shares=remaining_yes, no_shares=remaining_no)
    unwind_value = round(fill["fill_shares"] * fill["fill_price"], 6)
    await weather_db.record_weather_unwind(
        position["id"],
        unwind_collateral_usdc=unwind_value,
        status="partial_unwound" if remaining_yes == 0 and remaining_no == 0 else "open_partial",
        notes=f"Unwound unmatched {side} inventory at {fill['fill_price']:.4f}",
    )
    await weather_db.refresh_weather_position_balances(
        position["id"],
        yes_shares=remaining_yes,
        no_shares=remaining_no,
        paired_shares=paired,
        status="partial_unwound" if remaining_yes == 0 and remaining_no == 0 else "open_partial",
        notes=f"Unwound unmatched {side} inventory at {fill['fill_price']:.4f}",
    )
    if remaining_yes == 0 and remaining_no == 0:
        await weather_db.close_weather_merge_position(
            position["id"],
            status="partial_unwound",
            notes=f"Unwound unmatched {side} inventory at {fill['fill_price']:.4f}",
        )


async def _reconcile_position(clob, position: dict[str, Any], runtime) -> None:
    yes_balance = await asyncio.to_thread(_get_token_balance, clob, position["yes_token_id"])
    no_balance = await asyncio.to_thread(_get_token_balance, clob, position["no_token_id"])
    mergeable = compute_mergeable_shares(yes_shares=yes_balance, no_shares=no_balance)
    current_status = "open_paired" if mergeable > 0 else ("open_partial" if yes_balance > 0 or no_balance > 0 else "closed")
    await weather_db.refresh_weather_position_balances(
        position["id"],
        yes_shares=yes_balance,
        no_shares=no_balance,
        paired_shares=mergeable,
        status=current_status if current_status != "closed" else position["status"],
    )

    resolution = await weather_db.get_market_resolution(position["market_id"])
    resolved = bool((resolution or {}).get("resolved"))

    if mergeable > 0 and runtime.auto_merge and not resolved:
        merged_shares = mergeable
        result = await asyncio.to_thread(
            merge_position,
            position["condition_id"],
            neg_risk=bool(position.get("neg_risk")),
            shares=merged_shares,
        )
        await weather_db.record_weather_merge(
            position["id"],
            merged_shares=merged_shares,
            merged_collateral_usdc=float(merged_shares),
            mode=result.mode,
            transaction_hash=result.transaction_hash,
            state=result.state,
            status="merged",
        )
        yes_balance = await asyncio.to_thread(_get_token_balance, clob, position["yes_token_id"])
        no_balance = await asyncio.to_thread(_get_token_balance, clob, position["no_token_id"])
        mergeable = compute_mergeable_shares(yes_shares=yes_balance, no_shares=no_balance)
        await weather_db.refresh_weather_position_balances(
            position["id"],
            yes_shares=yes_balance,
            no_shares=no_balance,
            paired_shares=mergeable,
            status="open_partial" if (yes_balance > 0 or no_balance > 0) else "merged_closed",
        )
        if yes_balance == 0 and no_balance == 0:
            await weather_db.close_weather_merge_position(
                position["id"],
                status="merged_closed",
                notes=f"Merged {merged_shares} matched shares",
            )
            return

    if resolved and (yes_balance > 0 or no_balance > 0):
        result = await asyncio.to_thread(
            redeem_position,
            position["condition_id"],
            neg_risk=bool(position.get("neg_risk")),
            yes_shares=yes_balance,
            no_shares=no_balance,
        )
        winning_shares = max(yes_balance, no_balance)
        await weather_db.record_weather_redeem(
            position["id"],
            redeemed_collateral_usdc=winning_shares,
            mode=result.mode,
            transaction_hash=result.transaction_hash,
            state=result.state,
            status="redeemed",
        )
        await weather_db.close_weather_merge_position(
            position["id"],
            status="redeemed_closed",
            notes="Redeemed remaining resolved inventory",
        )
        return

    if mergeable == 0 and (yes_balance > 0 or no_balance > 0):
        opened_at = position.get("opened_at")
        if isinstance(opened_at, datetime):
            age_seconds = (datetime.now(UTC) - opened_at.astimezone(UTC)).total_seconds()
            if age_seconds >= runtime.partial_repair_window_seconds and not resolved:
                await _handle_partial_unwind(clob, position)


async def _attempt_entry(clob, candidate: dict[str, Any], plan: dict[str, Any], runtime, *, dry_run: bool) -> None:
    position_id = await weather_db.insert_weather_merge_position(
        plan=plan,
        max_complete_set_cost=runtime.live_rules["complete_set_cost_lte"],
        max_inventory_imbalance_ratio=runtime.live_rules.get("max_inventory_imbalance_ratio"),
    )

    if dry_run:
        await weather_db.close_weather_merge_position(
            position_id,
            status="dry_run",
            notes="Dry-run candidate only",
        )
        await _log_event(
            "weather_merge_dry_run",
            f"[WEATHER-MERGE] Dry run candidate {plan['city']} {plan['bucket_label']} | cost {plan['combined_cost']:.4f}",
            {"position_id": position_id, "plan": plan},
        )
        return

    first_side = plan["first_side"]
    second_side = plan["second_side"]
    first_token = plan["yes_token_id"] if first_side == "yes" else plan["no_token_id"]
    second_token = plan["yes_token_id"] if second_side == "yes" else plan["no_token_id"]
    first_price = plan["yes_price"] if first_side == "yes" else plan["no_price"]
    second_price = plan["yes_price"] if second_side == "yes" else plan["no_price"]
    target_shares = int(plan["target_shares"])

    first_fill = await asyncio.to_thread(
        _place_fok_order,
        clob,
        first_token,
        price=first_price,
        shares=target_shares,
        side="BUY",
    )
    if not first_fill:
        await weather_db.close_weather_merge_position(
            position_id,
            status="entry_failed",
            notes=f"First {first_side} leg did not fill",
        )
        return

    total_cost = first_fill["fill_shares"] * first_fill["fill_price"]
    await weather_db.record_weather_entry_fill(
        position_id,
        side=first_side,
        shares=first_fill["fill_shares"],
        fill_price=first_fill["fill_price"],
        order_id=first_fill.get("order_id"),
        total_entry_cost=total_cost,
        status="entry_first_leg_filled",
        notes=f"Filled {first_side} leg first",
    )

    max_second_leg_price = runtime.live_rules["complete_set_cost_lte"] - first_fill["fill_price"]
    if second_price > max_second_leg_price + 1e-9:
        await _handle_partial_unwind(
            clob,
            {
                "id": position_id,
                "yes_token_id": plan["yes_token_id"],
                "no_token_id": plan["no_token_id"],
                "yes_shares": first_fill["fill_shares"] if first_side == "yes" else 0.0,
                "no_shares": first_fill["fill_shares"] if first_side == "no" else 0.0,
            },
        )
        await weather_db.close_weather_merge_position(
            position_id,
            status="entry_failed",
            notes="Second leg moved above complete-set threshold",
        )
        return

    second_fill = await asyncio.to_thread(
        _place_fok_order,
        clob,
        second_token,
        price=second_price,
        shares=first_fill["fill_shares"],
        side="BUY",
    )
    if not second_fill:
        await _handle_partial_unwind(
            clob,
            {
                "id": position_id,
                "yes_token_id": plan["yes_token_id"],
                "no_token_id": plan["no_token_id"],
                "yes_shares": first_fill["fill_shares"] if first_side == "yes" else 0.0,
                "no_shares": first_fill["fill_shares"] if first_side == "no" else 0.0,
            },
        )
        await weather_db.close_weather_merge_position(
            position_id,
            status="entry_failed",
            notes=f"Second {second_side} leg did not fill",
        )
        return

    total_cost += second_fill["fill_shares"] * second_fill["fill_price"]
    await weather_db.record_weather_entry_fill(
        position_id,
        side=second_side,
        shares=second_fill["fill_shares"],
        fill_price=second_fill["fill_price"],
        order_id=second_fill.get("order_id"),
        total_entry_cost=total_cost,
        status="open_paired",
        notes="Both legs filled",
    )
    await weather_db.refresh_weather_position_balances(
        position_id,
        yes_shares=second_fill["fill_shares"] if second_side == "yes" else first_fill["fill_shares"],
        no_shares=second_fill["fill_shares"] if second_side == "no" else first_fill["fill_shares"],
        paired_shares=min(first_fill["fill_shares"], second_fill["fill_shares"]),
        status="open_paired",
    )
    await _log_event(
        "weather_merge_entry",
        f"[WEATHER-MERGE] Entered {plan['city']} {plan['bucket_label']} | {first_fill['fill_shares']} pairs @ {total_cost / max(first_fill['fill_shares'], 1):.4f}",
        {"position_id": position_id, "plan": plan, "total_cost": round(total_cost, 4)},
    )

    if runtime.auto_merge:
        await asyncio.sleep(config.SETTLEMENT_WAIT_SECONDS)
        position = {
            "id": position_id,
            "market_id": plan["market_id"],
            "condition_id": plan["condition_id"],
            "neg_risk": plan["neg_risk"],
            "yes_token_id": plan["yes_token_id"],
            "no_token_id": plan["no_token_id"],
            "opened_at": datetime.now(UTC),
            "status": "open_paired",
        }
        await _reconcile_position(clob, position, runtime)


async def _run_cycle(clob, bot_config: dict[str, Any], *, dry_run: bool) -> None:
    balance = await asyncio.to_thread(_get_usdc_balance, clob)
    runtime = build_runtime_config(
        bot_config,
        balance_usd=balance,
        sequence_budget_cap_usd=config.DEFAULT_SEQUENCE_BUDGET_USD,
        max_total_exposure_cap_usd=config.DEFAULT_MAX_TOTAL_EXPOSURE_USD,
        daily_loss_limit_cap_usd=config.DEFAULT_DAILY_LOSS_LIMIT_USD,
        min_expected_edge_usd=config.DEFAULT_MIN_EXPECTED_EDGE_USD,
        max_concurrent_positions=config.DEFAULT_MAX_CONCURRENT_POSITIONS,
        partial_repair_window_seconds=config.DEFAULT_PARTIAL_REPAIR_WINDOW_SECONDS,
        min_target_shares=config.DEFAULT_MIN_TARGET_SHARES,
        auto_merge=config.AUTO_MERGE and not dry_run,
    )

    daily_realized_pnl = await weather_db.get_daily_realized_pnl()
    daily_loss = max(0.0, -daily_realized_pnl)
    if daily_loss >= runtime.daily_loss_limit_usd:
        await _log_event(
            "weather_merge_paused",
            f"[WEATHER-MERGE] Daily loss limit reached ({daily_loss:.2f} / {runtime.daily_loss_limit_usd:.2f})",
            {"daily_loss": daily_loss, "daily_loss_limit_usd": runtime.daily_loss_limit_usd},
        )
        return

    positions = await weather_db.get_active_weather_merge_positions()
    for position in positions:
        await _reconcile_position(clob, position, runtime)

    positions = await weather_db.get_active_weather_merge_positions()
    active_exposure_usd = round(sum(open_position_exposure(position) for position in positions), 6)
    active_market_ids = {str(position.get("market_id")) for position in positions}
    if len(positions) >= runtime.max_concurrent_positions or active_exposure_usd >= runtime.max_total_exposure_usd:
        log.info(
            "[WEATHER-MERGE] Cycle OK | balance=%.2f active_positions=%d exposure=%.2f | stand_down=capacity_reached",
            balance,
            len(positions),
            active_exposure_usd,
        )
        return

    contexts = await fetch_active_weather_contexts(eligible_only=True)
    market_count = sum(len(context.markets) for context in contexts)
    candidates = rank_live_candidates(contexts, runtime, excluded_market_ids=active_market_ids)
    entry_limit = config.DEFAULT_MAX_ENTRY_ATTEMPTS if config.DEFAULT_MAX_ENTRY_ATTEMPTS > 0 else None
    entry_attempts = 0
    for candidate in candidates:
        positions = await weather_db.get_active_weather_merge_positions()
        active_exposure_usd = round(sum(open_position_exposure(position) for position in positions), 6)
        active_market_ids = {str(position.get("market_id")) for position in positions}
        if len(positions) >= runtime.max_concurrent_positions or active_exposure_usd >= runtime.max_total_exposure_usd:
            break
        if entry_limit is not None and entry_attempts >= entry_limit:
            break
        if str(candidate.get("market_id")) in active_market_ids:
            continue
        plan = plan_entry(candidate, runtime, active_exposure_usd=active_exposure_usd)
        if plan is None:
            continue
        await _attempt_entry(clob, candidate, plan, runtime, dry_run=dry_run)
        entry_attempts += 1

    final_positions = await weather_db.get_active_weather_merge_positions()
    final_exposure_usd = round(sum(open_position_exposure(position) for position in final_positions), 6)
    log.info(
        _cycle_status_message(
            balance=balance,
            active_positions=len(final_positions),
            active_exposure_usd=final_exposure_usd,
            context_count=len(contexts),
            market_count=market_count,
            candidate_count=len(candidates),
            entry_attempts=entry_attempts,
            top_candidate=candidates[0] if candidates else None,
        )
    )


async def run(*, config_path: str, dry_run: bool, once: bool) -> None:
    trading_config.patch_clob_client_proxy(PROXY_URL)
    await init_pool()
    await trading_db.create_trading_tables()
    await create_weather_tables()
    await weather_db.create_weather_merge_tables()

    bot_config = _load_bot_config(config_path)
    clob = _build_clob_client()

    if not dry_run:
        approval_state = await asyncio.to_thread(ensure_weather_allowances, auto_approve=config.AUTO_APPROVE)
        if not approval_state.ready:
            raise RuntimeError("Weather bot approvals are not ready")

    await _log_event(
        "weather_merge_start",
        f"[WEATHER-MERGE] Bot started | mode={'DRY RUN' if dry_run else 'LIVE'} | config={config_path}",
        {"dry_run": dry_run, "config_path": config_path},
    )

    while True:
        try:
            await _run_cycle(clob, bot_config, dry_run=dry_run)
        except Exception as exc:
            await _log_event(
                "weather_merge_error",
                f"[WEATHER-MERGE] Cycle failed: {type(exc).__name__}: {exc}",
                {"error": str(exc), "error_type": type(exc).__name__},
            )
        if once:
            return
        await asyncio.sleep(config.DEFAULT_LOOP_INTERVAL_SECONDS)


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run(config_path=args.config_path, dry_run=args.dry_run, once=args.once))
    except KeyboardInterrupt:
        log.info("[WEATHER-MERGE] Stopped by operator")
    finally:
        try:
            asyncio.run(close_pool())
        except Exception:
            pass


if __name__ == "__main__":
    main()
