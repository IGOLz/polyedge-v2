"""PolyEdge trading bot for Polymarket crypto markets."""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from datetime import datetime, timezone

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, AssetType, BalanceAllowanceParams

from shared.config import PROXY_URL
from shared.db import close_pool, create_weather_tables, init_pool
from trading import config
from trading import db
from trading.balance import get_usdc_balance
from trading.executor import (
    cancel_stop_loss_order,
    cancel_take_profit_order,
    execute_limit_exit_order,
    execute_trade,
    force_close_position,
    get_execution_metrics,
    get_best_sell_price,
    get_variance_metrics,
    place_stop_loss_order,
    record_trade_outcome,
    sync_daily_net_loss_from_db,
)
from trading.live_profile import live_profile_summary, market_in_live_scope
from trading.meta_selector import live_meta_selector_summary
from trading.redeemer import (
    describe_redemption_mode,
    redemption_loop,
    startup_redemption_preflight,
)
from trading.report import generate_live_reports
from trading.strategy_adapter import evaluate_strategies
from trading.weather_runtime import weather_loop
from trading.utils import debug_log, log, strategy_log_tag


def _get_live_float(live_config: dict[str, str], key: str, fallback: float) -> float:
    raw_value = live_config.get(key)
    if raw_value is None:
        return fallback
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        log.warning(
            "Invalid live config value for %s=%r - using fallback %.2f",
            key,
            raw_value,
            fallback,
        )
        return fallback


def build_clob_client() -> ClobClient:
    creds = ApiCreds(
        api_key=config.API_KEY,
        api_secret=config.API_SECRET,
        api_passphrase=config.API_PASSPHRASE,
    )
    return ClobClient(
        config.CLOB_BASE_URL,
        key=config.PRIVATE_KEY,
        chain_id=137,
        creds=creds,
        signature_type=2,
        funder=config.PROXY_WALLET,
    )


def _spawn_background_task(coro, *, name: str) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)

    def _report_failure(done_task: asyncio.Task) -> None:
        if done_task.cancelled():
            return
        exc = done_task.exception()
        if exc is not None:
            log.exception(
                "[TASK] %s crashed: %s: %r",
                name,
                type(exc).__name__,
                exc,
                exc_info=exc,
            )

    task.add_done_callback(_report_failure)
    return task


async def verify_proxy() -> None:
    if not PROXY_URL:
        log.warning("No PROXY_URL set - traffic routes directly")
        return
    try:
        async with config.get_http_client() as client:
            resp = await client.get("https://api64.ipify.org?format=json")
            ip = resp.json()["ip"]
            log.info("Proxy active - outbound IP: %s", ip)
    except Exception as exc:
        log.critical("Proxy connection failed: %s - fix PROXY_URL or remove it", exc)
        sys.exit(1)


async def heartbeat_loop() -> None:
    while True:
        now = datetime.now(timezone.utc)
        message = f"[HEARTBEAT] Bot alive - {now.strftime('%H:%M:%S')}"
        log.info(message)
        await db.log_event(
            "trading_heartbeat",
            message,
            {"heartbeat_at": now.isoformat()},
            echo=False,
        )
        await asyncio.sleep(60)


def _fmt_market(mt: str) -> str:
    parts = mt.split("_")
    return f"{parts[0].upper()} {parts[1]}" if len(parts) == 2 else mt


def _extract_exit_fill(
    order: dict | None, fallback_price: float, fallback_shares: float
) -> tuple[float, int]:
    fill_price = fallback_price
    fill_shares = max(0, math.floor(fallback_shares))
    if isinstance(order, dict):
        raw_price = order.get("average_price") or order.get("price")
        raw_shares = (
            order.get("size_matched") or order.get("matched_size") or order.get("filled")
        )
        if raw_price is not None:
            fill_price = float(raw_price)
        if raw_shares is not None:
            fill_shares = max(0, math.floor(float(raw_shares)))
    return fill_price, fill_shares


async def _cancel_sibling_exit_order(clob, trade, filled_exit: str) -> None:
    sibling_kind = "take_profit" if filled_exit == "stop_loss" else "stop_loss"
    sibling_order_id = trade.get(f"{sibling_kind}_order_id")
    if not sibling_order_id:
        return

    try:
        if sibling_kind == "take_profit":
            await cancel_take_profit_order(clob, trade["id"], sibling_order_id)
        else:
            await cancel_stop_loss_order(clob, trade["id"], sibling_order_id)
    except Exception as exc:
        log.warning(
            "[EXIT] Failed to cancel sibling %s order for trade %s: %s",
            sibling_kind,
            trade["id"],
            exc,
        )


async def _handle_exit_fill(clob, trade, exit_kind: str, order_id: str, order: dict | None) -> None:
    price_key = "take_profit_price" if exit_kind == "take_profit" else "stop_loss_price"
    fallback_price = float(trade[price_key] or 0.0)
    exit_price, exit_shares = _extract_exit_fill(
        order,
        fallback_price,
        float(trade["shares"] or 0.0),
    )
    market_label = _fmt_market(trade["market_type"])
    entry_price = float(trade["entry_price"])
    gross_exit = exit_price * exit_shares
    est_pnl = (exit_price - entry_price) * exit_shares
    label = "Take-profit" if exit_kind == "take_profit" else "Stop-loss"
    log_type = "trade_take_profit" if exit_kind == "take_profit" else "trade_stop_loss"

    log.info(
        "[EXIT] %s filled - %s %s on %s | %d shares @ %.4f ($%.2f) | est pnl: %+.2f | order=%s",
        label,
        trade["strategy_name"],
        trade["direction"],
        market_label,
        exit_shares,
        exit_price,
        gross_exit,
        est_pnl,
        order_id[:16],
    )
    await db.log_event(
        log_type,
        f"{label} exit - {trade['strategy_name']} {trade['direction']} on {trade['market_type']} | "
        f"{exit_shares} shares @ {exit_price:.4f} | est pnl {est_pnl:+.2f}",
        {
            "trade_id": trade["id"],
            "market_id": trade["market_id"],
            "strategy_name": trade["strategy_name"],
            "direction": trade["direction"],
            "entry_price": entry_price,
            "exit_price": round(exit_price, 4),
            "exit_shares": exit_shares,
            "gross_exit_value": round(gross_exit, 2),
            "estimated_pnl": round(est_pnl, 2),
            f"{exit_kind}_order_id": order_id,
        },
    )

    if exit_kind == "take_profit":
        await db.mark_take_profit_triggered(
            trade["id"],
            exit_price,
            exit_shares=exit_shares,
        )
    else:
        await db.mark_stop_loss_triggered(
            trade["id"],
            exit_price,
            exit_shares=exit_shares,
        )
    record_trade_outcome((exit_price - entry_price) * exit_shares)

    await _cancel_sibling_exit_order(clob, trade, exit_kind)


async def outcome_tracker_loop(clob) -> None:
    log.info("Outcome tracker started (every 5 min)")
    while True:
        try:
            resolved = await db.update_pending_outcomes(clob)
            for trade in resolved:
                tag = strategy_log_tag(trade["strategy_name"])
                market_label = _fmt_market(trade["market_type"])
                pnl = trade["pnl"]
                record_trade_outcome(pnl)

                if trade["result"] == "win_resolution":
                    log.info(
                        "[%s] %s | %s -> WIN | PnL: +$%.2f",
                        tag,
                        market_label,
                        trade["market_id"][:12],
                        abs(pnl),
                    )
                else:
                    log.warning(
                        "[%s] %s | %s -> LOSS | PnL: -$%.2f",
                        tag,
                        market_label,
                        trade["market_id"][:12],
                        abs(pnl),
                    )

                await db.log_event(
                    f"trade_{trade['result']}",
                    f"[{tag}] {market_label} -> {trade['result'].upper()} | PnL: {pnl:+.2f}",
                    {
                        "trade_id": trade["trade_id"],
                        "market_id": trade["market_id"],
                        "strategy_name": trade["strategy_name"],
                        "direction": trade["direction"],
                        "pnl": pnl,
                    },
                )

            if resolved:
                wins = sum(1 for trade in resolved if trade["result"] == "win_resolution")
                total_pnl = sum(trade["pnl"] for trade in resolved)
                balance = await get_usdc_balance()
                log.info(
                    "Outcome batch: %d resolved (%d WIN) | Batch PnL: %+.2f | Balance: $%.2f",
                    len(resolved),
                    wins,
                    total_pnl,
                    max(balance, 0),
                )
        except Exception:
            log.exception("Error in outcome tracker")
        await asyncio.sleep(300)


async def stop_loss_monitor_loop(clob) -> None:
    log.info("Stop-loss monitor started (every 30s)")
    while True:
        try:
            open_stop_losses = await db.get_open_stop_loss_orders()
            for trade in open_stop_losses:
                order_id = trade["stop_loss_order_id"]
                try:
                    loop = asyncio.get_event_loop()
                    order = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda oid=order_id: clob.get_order(oid)),
                        timeout=10.0,
                    )
                    status = order.get("status", "") if isinstance(order, dict) else ""
                    if status in ("FILLED", "MATCHED"):
                        exit_price, exit_shares = _extract_exit_fill(
                            order,
                            float(trade["stop_loss_price"] or 0.0),
                            float(trade["shares"] or 0.0),
                        )
                        market_label = _fmt_market(trade["market_type"])
                        entry_price = float(trade["entry_price"])
                        gross_exit = exit_price * exit_shares
                        est_pnl = (exit_price - entry_price) * exit_shares
                        log.info(
                            "[EXIT] Stop-loss filled - %s %s on %s | %d shares @ %.4f ($%.2f) | est pnl: %+.2f | order=%s",
                            trade["strategy_name"],
                            trade["direction"],
                            market_label,
                            exit_shares,
                            exit_price,
                            gross_exit,
                            est_pnl,
                            order_id[:16],
                        )
                        await db.log_event(
                            "trade_stop_loss",
                            f"Stop-loss exit - {trade['strategy_name']} {trade['direction']} on {trade['market_type']} | "
                            f"{exit_shares} shares @ {exit_price:.4f} | est pnl {est_pnl:+.2f}",
                            {
                                "trade_id": trade["id"],
                                "market_id": trade["market_id"],
                                "strategy_name": trade["strategy_name"],
                                "direction": trade["direction"],
                                "entry_price": entry_price,
                                "exit_price": round(exit_price, 4),
                                "exit_shares": exit_shares,
                                "gross_exit_value": round(gross_exit, 2),
                                "estimated_pnl": round(est_pnl, 2),
                                "stop_loss_order_id": order_id,
                            },
                        )
                        await db.mark_stop_loss_triggered(
                            trade["id"],
                            exit_price,
                            exit_shares=exit_shares,
                        )
                        record_trade_outcome((exit_price - entry_price) * exit_shares)
                except Exception as exc:
                    log.warning("[STOP-LOSS] Check failed: %s", exc)
        except Exception as exc:
            log.error("[STOP-LOSS] Monitor error: %s: %r", type(exc).__name__, exc)
        await asyncio.sleep(30)


async def exit_monitor_loop(clob) -> None:
    log.info("Exit monitor started (every 30s)")
    while True:
        try:
            open_exits = await db.get_open_exit_orders()
            for trade_row in open_exits:
                trade = dict(trade_row)
                loop = asyncio.get_event_loop()
                exit_resolved = False

                tp_price = (
                    float(trade["take_profit_price"])
                    if trade.get("take_profit_price") is not None
                    else None
                )
                if tp_price is not None and not trade.get("take_profit_triggered"):
                    try:
                        best_sell = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                lambda token_id=trade["token_id"]: get_best_sell_price(clob, token_id),
                            ),
                            timeout=5.0,
                        )
                        if best_sell is not None and best_sell >= tp_price:
                            log.info(
                                "[EXIT] Take-profit threshold reached for trade %s | best bid %.4f >= target %.4f",
                                trade["id"],
                                best_sell,
                                tp_price,
                            )
                            stop_loss_order_id = trade.get("stop_loss_order_id")
                            if stop_loss_order_id:
                                try:
                                    cancel_status, cancelled_order = await cancel_stop_loss_order(
                                        clob,
                                        trade["id"],
                                        stop_loss_order_id,
                                    )
                                    if cancel_status in ("FILLED", "MATCHED"):
                                        await _handle_exit_fill(
                                            clob,
                                            trade,
                                            "stop_loss",
                                            stop_loss_order_id,
                                            cancelled_order,
                                        )
                                        exit_resolved = True
                                        continue
                                    if cancel_status not in ("CANCELLED", "EXPIRED"):
                                        log.warning(
                                            "[EXIT] Stop-loss cancellation not confirmed for trade %s - deferring take-profit",
                                            trade["id"],
                                        )
                                        continue
                                    trade["stop_loss_order_id"] = None
                                except Exception as exc:
                                    log.warning(
                                        "[EXIT] Could not cancel stop-loss before take-profit for trade %s: %s",
                                        trade["id"],
                                        exc,
                                    )
                                    continue

                            if exit_resolved:
                                continue

                            exit_fill = await execute_limit_exit_order(
                                clob,
                                trade["token_id"],
                                float(trade["shares"] or 0.0),
                                tp_price,
                                log_prefix="TAKE-PROFIT",
                                trade_id=trade["id"],
                                initial_delay=0.5,
                                timeout=3.0,
                                balance_attempts=10,
                            )
                            if exit_fill:
                                synthetic_order = {
                                    "average_price": exit_fill["fill_price"],
                                    "matched_size": exit_fill["fill_shares"],
                                    "status": "FILLED",
                                }
                                tp_order_id = str(exit_fill.get("order_id") or f"software-tp-{trade['id']}")
                                await _handle_exit_fill(clob, trade, "take_profit", tp_order_id, synthetic_order)
                                exit_resolved = True
                                continue

                            log.warning(
                                "[EXIT] Software take-profit trigger failed to execute for trade %s",
                                trade["id"],
                            )
                            if stop_loss_order_id and trade.get("stop_loss_price") is not None:
                                new_stop_loss = await place_stop_loss_order(
                                    clob=clob,
                                    trade_id=trade["id"],
                                    token_id=trade["token_id"],
                                    shares=float(trade["shares"] or 0.0),
                                    stop_loss_price=float(trade["stop_loss_price"]),
                                    initial_delay=0.5,
                                    balance_attempts=10,
                                )
                                if new_stop_loss is None:
                                    log.error(
                                        "[EXIT] Trade %s is unprotected after failed software take-profit",
                                        trade["id"],
                                    )
                                    await db.log_event(
                                        "trade_unprotected",
                                        f"Trade {trade['id']} lost stop-loss protection after failed software take-profit",
                                        {
                                            "trade_id": trade["id"],
                                            "market_id": trade["market_id"],
                                            "strategy_name": trade["strategy_name"],
                                            "direction": trade["direction"],
                                        },
                                    )
                                else:
                                    log.info(
                                        "[EXIT] Re-armed stop-loss for trade %s after failed software take-profit",
                                        trade["id"],
                                    )
                                    await db.log_event(
                                        "trade_protection_rearmed",
                                        f"Re-armed stop-loss for trade {trade['id']} after failed software take-profit",
                                        {
                                            "trade_id": trade["id"],
                                            "market_id": trade["market_id"],
                                            "strategy_name": trade["strategy_name"],
                                            "direction": trade["direction"],
                                        },
                                    )
                    except Exception as exc:
                        log.warning(
                            "[EXIT] Software take-profit check failed for trade %s: %s",
                            trade["id"],
                            exc,
                        )

                if exit_resolved:
                    continue

                for exit_kind in ("take_profit", "stop_loss"):
                    order_id = trade.get(f"{exit_kind}_order_id")
                    if not order_id or trade.get(f"{exit_kind}_triggered"):
                        continue

                    try:
                        order = await asyncio.wait_for(
                            loop.run_in_executor(None, lambda oid=order_id: clob.get_order(oid)),
                            timeout=10.0,
                        )
                        status = (order.get("status") or "").upper() if isinstance(order, dict) else ""
                        if status in ("FILLED", "MATCHED"):
                            await _handle_exit_fill(clob, trade, exit_kind, order_id, order)
                            exit_resolved = True
                            break
                        if status in ("CANCELLED", "EXPIRED"):
                            if exit_kind == "take_profit":
                                await db.mark_take_profit_cancelled(trade["id"])
                            else:
                                await db.mark_stop_loss_cancelled(trade["id"])
                            log.warning(
                                "[EXIT] %s order %s for trade %s is %s",
                                exit_kind,
                                order_id[:16],
                                trade["id"],
                                status,
                            )
                            if exit_kind == "stop_loss" and trade.get("stop_loss_price") is not None:
                                new_stop_loss = await place_stop_loss_order(
                                    clob=clob,
                                    trade_id=trade["id"],
                                    token_id=trade["token_id"],
                                    shares=float(trade["shares"] or 0.0),
                                    stop_loss_price=float(trade["stop_loss_price"]),
                                    initial_delay=0.0,
                                )
                                if new_stop_loss is None:
                                    forced_exit = await force_close_position(
                                        clob,
                                        trade["token_id"],
                                        shares=float(trade["shares"] or 0.0),
                                        trade_id=trade["id"],
                                        reason=f"stop-loss order {status.lower()}",
                                    )
                                    if forced_exit:
                                        synthetic_order = {
                                            "average_price": forced_exit["fill_price"],
                                            "matched_size": forced_exit["fill_shares"],
                                            "status": "FILLED",
                                        }
                                        forced_order_id = str(
                                            forced_exit.get("order_id") or f"forced-stop-loss-{trade['id']}"
                                        )
                                        await _handle_exit_fill(
                                            clob,
                                            trade,
                                            "stop_loss",
                                            forced_order_id,
                                            synthetic_order,
                                        )
                                        exit_resolved = True
                                        break
                                    await db.log_event(
                                        "trade_unprotected",
                                        f"Trade {trade['id']} lost stop-loss protection after {status.lower()} order",
                                        {
                                            "trade_id": trade["id"],
                                            "market_id": trade["market_id"],
                                            "strategy_name": trade["strategy_name"],
                                            "direction": trade["direction"],
                                        },
                                    )
                                else:
                                    log.info(
                                        "[EXIT] Re-armed stop-loss for trade %s after %s order",
                                        trade["id"],
                                        status.lower(),
                                    )
                                    await db.log_event(
                                        "trade_protection_rearmed",
                                        f"Re-armed stop-loss for trade {trade['id']} after {status.lower()} order",
                                        {
                                            "trade_id": trade["id"],
                                            "market_id": trade["market_id"],
                                            "strategy_name": trade["strategy_name"],
                                            "direction": trade["direction"],
                                            "previous_status": status,
                                        },
                                    )
                    except Exception as exc:
                        log.warning(
                            "[EXIT] %s check failed for trade %s: %s",
                            exit_kind,
                            trade["id"],
                            exc,
                        )

                if exit_resolved:
                    continue
        except Exception as exc:
            log.error("[EXIT] Monitor error: %s: %r", type(exc).__name__, exc)
        await asyncio.sleep(30)


async def hourly_summary_loop() -> None:
    log.info("Hourly summary loop started")
    while True:
        await asyncio.sleep(3600)
        try:
            stats = await db.get_bot_stats()
            balance = await get_usdc_balance()
            metrics = get_execution_metrics()
            if metrics.total > 0:
                log.info("[EXEC METRICS] %s", metrics.summary())
            await db.log_event(
                "hourly_summary",
                f"ROI: {stats.roi:.1f}% | Balance: ${balance:.2f}",
                {
                    "total_trades": stats.total_trades,
                    "wins": stats.wins,
                    "total_pnl": round(stats.total_pnl, 2),
                    "balance": balance,
                },
            )
        except Exception:
            log.exception("Error in hourly summary")


async def strategy_report_loop() -> None:
    """Generate per-strategy reports every hour."""
    log.info("Strategy report loop started (every 1h, 5min offset)")
    await asyncio.sleep(300)
    while True:
        try:
            reports = await generate_live_reports(output_dir="./reports/live")
            if reports:
                log.info("[REPORT] Updated %d strategy report(s)", len(reports))
        except Exception:
            log.exception("Error generating strategy reports")
        await asyncio.sleep(3600)


async def run() -> None:
    await verify_proxy()
    config.patch_clob_client_proxy(PROXY_URL)

    await init_pool()
    await db.create_trading_tables()
    await create_weather_tables()
    await db.seed_config_if_empty(
        {
            "strategy_momentum_enabled": str(config.STRATEGY_MOMENTUM_ENABLED).lower(),
            "bet_size_usd": str(config.BET_SIZE_USD),
            "daily_loss_limit": str(config.DAILY_LOSS_LIMIT),
            "weather_enabled": "false",
            "weather_probe_bet_size_usd": str(max(config.MIN_LIVE_BET_SIZE_USD, 5.0)),
            "weather_daily_loss_limit": "10.0",
            "weather_max_concurrent_events": "2",
            "weather_shadow_only": "true",
        }
    )

    clob = build_clob_client()

    try:
        bal = clob.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        balance = int(bal.get("balance", "0")) / 1_000_000
    except Exception:
        log.critical("Could not fetch balance - check connectivity")
        raise SystemExit(1)

    log.info("USDC balance: $%.2f", balance)
    log.info("Live strategy profile: %s", live_profile_summary())

    try:
        await db.update_pending_outcomes(clob)
        log.info("Startup outcome resolution complete")
    except Exception:
        log.exception("Error resolving outcomes on startup")
    await sync_daily_net_loss_from_db()
    startup_live_config = await db.get_live_config()
    startup_bet_size = _get_live_float(startup_live_config, "bet_size_usd", config.BET_SIZE_USD)
    startup_daily_loss_limit = _get_live_float(
        startup_live_config,
        "daily_loss_limit",
        config.DAILY_LOSS_LIMIT,
    )

    redemption_mode = "disabled_in_dry_run"
    if config.DRY_RUN:
        log.info("[DRY RUN] Mode active - no real orders")
    else:
        preflight = await startup_redemption_preflight()
        redemption_mode = str(preflight.get("mode") or describe_redemption_mode())

    await db.log_event(
        "bot_start",
        "Bot started",
        {
            "bet_size": startup_bet_size,
            "daily_loss_limit": startup_daily_loss_limit,
            "balance": balance,
            "dry_run": config.DRY_RUN,
            "live_profile": live_profile_summary(),
            "meta_selector": live_meta_selector_summary(),
            "redemption_mode": redemption_mode,
        },
    )

    _spawn_background_task(heartbeat_loop(), name="heartbeat")
    _spawn_background_task(outcome_tracker_loop(clob), name="outcome-tracker")
    if not config.DRY_RUN:
        _spawn_background_task(redemption_loop(), name="redemption-loop")
    else:
        log.info("[DRY RUN] Redemption loop disabled")
    _spawn_background_task(exit_monitor_loop(clob), name="exit-monitor")
    _spawn_background_task(hourly_summary_loop(), name="hourly-summary")
    _spawn_background_task(strategy_report_loop(), name="strategy-report")
    _spawn_background_task(weather_loop(clob), name="weather-loop")

    log.info(
        "Bot started - mode=%s | redemption=%s | %s | $%.2f/trade | loss limit $%.2f",
        "DRY RUN" if config.DRY_RUN else "LIVE",
        redemption_mode,
        live_meta_selector_summary(),
        startup_bet_size,
        startup_daily_loss_limit,
    )

    backoff = 0
    while True:
        try:
            live_config = await db.get_live_config()
            all_active_markets = await db.get_active_markets()
            active_markets = [
                market
                for market in all_active_markets
                if market_in_live_scope(market.market_type, market.started_at)
            ]

            for market in active_markets:
                ticks = await db.get_market_ticks(market.market_id, market.started_at)
                signals = await evaluate_strategies(market, ticks)
                for signal in signals:
                    await execute_trade(clob, market, signal, live_config)

            backoff = 0
        except Exception as exc:
            log.exception("Strategy loop error")
            await db.log_event("bot_error", f"Strategy loop error - {exc}", {"error": str(exc)})
            backoff = min(backoff + 1, 6)
            await asyncio.sleep(config.LOOP_INTERVAL * (2**backoff))
            continue

        await asyncio.sleep(config.LOOP_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser(description="PolyEdge trading bot")
    parser.add_argument("--dry-run", action="store_true", help="No real orders")
    args = parser.parse_args()

    if args.dry_run:
        config.DRY_RUN = True

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Shutting down (KeyboardInterrupt)")
    finally:
        try:
            asyncio.run(close_pool())
        except Exception:
            pass


if __name__ == "__main__":
    main()
