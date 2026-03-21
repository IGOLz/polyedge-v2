"""PolyEdge Trading Bot — strategy-based trading bot for Polymarket crypto markets."""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from datetime import datetime, timezone

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, BalanceAllowanceParams, AssetType

from shared.config import PROXY_URL
from shared.db import init_pool, close_pool
from trading import config
from trading import db
from trading.balance import get_usdc_balance
from trading.executor import execute_trade, get_execution_metrics, get_variance_metrics
from trading.live_profile import live_profile_summary, market_in_live_scope
from trading.redeemer import redemption_loop
from trading.report import generate_live_reports
from trading.strategy_adapter import evaluate_strategies
from trading.utils import debug_log, log, strategy_log_tag


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


async def verify_proxy() -> None:
    if not PROXY_URL:
        log.warning("No PROXY_URL set — traffic routes directly")
        return
    try:
        async with config.get_http_client() as client:
            resp = await client.get("https://api64.ipify.org?format=json")
            ip = resp.json()["ip"]
            log.info("Proxy active — outbound IP: %s", ip)
    except Exception as e:
        log.critical("Proxy connection failed: %s — fix PROXY_URL or remove it", e)
        sys.exit(1)


async def heartbeat_loop() -> None:
    while True:
        log.info("[HEARTBEAT] Bot alive — %s", datetime.now(timezone.utc).strftime('%H:%M:%S'))
        await asyncio.sleep(10)


def _fmt_market(mt: str) -> str:
    parts = mt.split("_")
    return f"{parts[0].upper()} {parts[1]}" if len(parts) == 2 else mt


def _extract_exit_fill(order: dict | None, fallback_price: float, fallback_shares: float) -> tuple[float, int]:
    fill_price = fallback_price
    fill_shares = max(0, math.floor(fallback_shares))
    if isinstance(order, dict):
        raw_price = order.get("average_price") or order.get("price")
        raw_shares = order.get("size_matched") or order.get("matched_size") or order.get("filled")
        if raw_price is not None:
            fill_price = float(raw_price)
        if raw_shares is not None:
            fill_shares = max(0, math.floor(float(raw_shares)))
    return fill_price, fill_shares


async def outcome_tracker_loop(clob) -> None:
    log.info("Outcome tracker started (every 5 min)")
    while True:
        try:
            resolved = await db.update_pending_outcomes(clob)
            for t in resolved:
                tag = strategy_log_tag(t["strategy_name"])
                market_label = _fmt_market(t["market_type"])
                pnl = t["pnl"]

                if t["result"] == "win":
                    log.info("[%s] %s | %s → ✅ WIN | PnL: +$%.2f", tag, market_label, t["market_id"][:12], abs(pnl))
                else:
                    log.warning("[%s] %s | %s → ❌ LOSS | PnL: -$%.2f", tag, market_label, t["market_id"][:12], abs(pnl))

                await db.log_event(f"trade_{t['result']}", f"[{tag}] {market_label} → {t['result'].upper()} | PnL: {pnl:+.2f}", {
                    "trade_id": t["trade_id"], "market_id": t["market_id"],
                    "strategy_name": t["strategy_name"], "direction": t["direction"],
                    "pnl": pnl,
                })

            if resolved:
                wins = sum(1 for t in resolved if t["result"] == "win")
                total_pnl = sum(t["pnl"] for t in resolved)
                balance = await get_usdc_balance()
                log.info("Outcome batch: %d resolved (%d WIN) | Batch PnL: %+.2f | Balance: $%.2f",
                         len(resolved), wins, total_pnl, max(balance, 0))
        except Exception:
            log.exception("Error in outcome tracker")
        await asyncio.sleep(300)


async def stop_loss_monitor_loop(clob) -> None:
    log.info("Stop-loss monitor started (every 30s)")
    while True:
        try:
            open_stop_losses = await db.get_open_stop_loss_orders()
            for trade in open_stop_losses:
                order_id = trade['stop_loss_order_id']
                try:
                    loop = asyncio.get_event_loop()
                    order = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda oid=order_id: clob.get_order(oid)), timeout=10.0)
                    status = order.get('status', '') if isinstance(order, dict) else ''
                    if status in ('FILLED', 'MATCHED'):
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
                            "[EXIT] Stop-loss filled — %s %s on %s | %d shares @ %.4f ($%.2f) | est pnl: %+.2f | order=%s",
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
                            f"Stop-loss exit — {trade['strategy_name']} {trade['direction']} on {trade['market_type']} | "
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
                        await db.mark_stop_loss_triggered(trade['id'])
                except Exception as e:
                    log.warning("[STOP-LOSS] Check failed: %s", e)
        except Exception as e:
            log.error("[STOP-LOSS] Monitor error: %s", e)
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
            await db.log_event("hourly_summary", f"ROI: {stats.roi:.1f}% | Balance: ${balance:.2f}", {
                "total_trades": stats.total_trades, "wins": stats.wins,
                "total_pnl": round(stats.total_pnl, 2), "balance": balance,
            })
        except Exception:
            log.exception("Error in hourly summary")


async def strategy_report_loop() -> None:
    """Generate per-strategy reports every hour (offset from hourly summary)."""
    log.info("Strategy report loop started (every 1h, 5min offset)")
    await asyncio.sleep(300)  # offset so it doesn't overlap with hourly_summary
    while True:
        try:
            reports = await generate_live_reports(output_dir="./reports/live")
            if reports:
                log.info("[REPORT] Updated %d strategy report(s)", len(reports))
        except Exception:
            log.exception("Error generating strategy reports")
        await asyncio.sleep(3600)


async def run() -> None:
    asyncio.create_task(heartbeat_loop())

    await verify_proxy()
    config.patch_clob_client_proxy(PROXY_URL)

    # Init shared DB pool + trading tables
    await init_pool()
    await db.create_trading_tables()
    await db.seed_config_if_empty({
        'strategy_momentum_enabled': str(config.STRATEGY_MOMENTUM_ENABLED).lower(),
        'bet_size_usd': str(config.BET_SIZE_USD),
        'daily_loss_limit': str(config.DAILY_LOSS_LIMIT),
    })

    clob = build_clob_client()

    try:
        bal = clob.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        balance = int(bal.get("balance", "0")) / 1_000_000
    except Exception:
        log.critical("Could not fetch balance — check connectivity")
        raise SystemExit(1)

    log.info("USDC balance: $%.2f", balance)
    log.info("Live strategy profile: %s", live_profile_summary())

    try:
        await db.update_pending_outcomes(clob)
        log.info("Startup outcome resolution complete")
    except Exception:
        log.exception("Error resolving outcomes on startup")

    if config.DRY_RUN:
        log.info("[DRY RUN] Mode active — no real orders")

    await db.log_event("bot_start", "Bot started", {
        "bet_size": config.BET_SIZE_USD, "daily_loss_limit": config.DAILY_LOSS_LIMIT,
        "balance": balance, "dry_run": config.DRY_RUN,
        "live_profile": live_profile_summary(),
    })

    asyncio.create_task(outcome_tracker_loop(clob))
    if not config.DRY_RUN:
        asyncio.create_task(redemption_loop())
    else:
        log.info("[DRY RUN] Redemption loop disabled")
    asyncio.create_task(stop_loss_monitor_loop(clob))
    asyncio.create_task(hourly_summary_loop())
    asyncio.create_task(strategy_report_loop())

    log.info("Bot started — mode=%s | $%.2f/trade | loss limit $%.2f",
             "DRY RUN" if config.DRY_RUN else "LIVE", config.BET_SIZE_USD, config.DAILY_LOSS_LIMIT)

    # ── Main strategy evaluation loop ───────────────────────────────
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
            await db.log_event("bot_error", f"Strategy loop error — {exc}", {"error": str(exc)})
            backoff = min(backoff + 1, 6)
            await asyncio.sleep(config.LOOP_INTERVAL * (2 ** backoff))
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


if __name__ == "__main__":
    main()
