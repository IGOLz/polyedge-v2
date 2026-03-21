"""Live trading strategy reports — same format as backtest reports.

Queries ``bot_trades`` per strategy, computes the full metric set
(matching ``engine.compute_metrics`` output), and generates per-strategy
:class:`StrategyReport` files in JSON + Markdown.

Designed to run periodically in the trading bot's event loop via
:func:`generate_live_reports`.

Usage from bot loop::

    from trading.report import generate_live_reports
    await generate_live_reports(output_dir="./reports/live")

Manual / debug::

    cd src && PYTHONPATH=. python3 -m trading.report
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from shared.db import get_pool, init_pool
from shared.strategies.report import StrategyReport

logger = logging.getLogger("polyedge.trading.report")


# ── Raw trade query ─────────────────────────────────────────────────


async def _fetch_resolved_trades() -> list[dict]:
    """Fetch all filled+resolved trades from bot_trades.

    Returns dicts with keys matching what ``compute_live_metrics`` needs.
    Only includes trades with a definitive outcome (take profit, resolution win, stop loss, loss).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                id,
                market_id,
                market_type,
                strategy_name,
                direction,
                entry_price,
                bet_size_usd,
                shares,
                final_outcome,
                pnl,
                stop_loss_price,
                take_profit_price,
                placed_at,
                resolved_at,
                signal_data
            FROM bot_trades
            WHERE status = 'filled'
              AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')
            ORDER BY placed_at ASC
        """)

    trades = []
    for r in rows:
        entry_price = float(r["entry_price"])
        bet_size = float(r["bet_size_usd"])
        shares = float(r["shares"]) if r["shares"] is not None else (
            bet_size / entry_price if entry_price > 0 else 0
        )
        raw_outcome = r["final_outcome"]
        outcome = "win" if raw_outcome in ("win_resolution", "take_profit") else "loss"
        pnl = float(r["pnl"]) if r["pnl"] is not None else (
            shares * (1.0 - entry_price) if raw_outcome == "win_resolution"
            else (float(r["take_profit_price"] or 0) - entry_price) * shares if raw_outcome == "take_profit"
            else (float(r["stop_loss_price"] or 0) - entry_price) * shares if raw_outcome == "stop_loss"
            else -bet_size
        )

        # Extract asset and duration from market_type (e.g. "btc_5m")
        market_type = r["market_type"] or ""
        parts = market_type.split("_")
        asset = parts[0].upper() if parts else ""
        duration_minutes = int(parts[1].replace("m", "")) if len(parts) >= 2 and parts[1].endswith("m") else 0

        trades.append({
            "trade_id": r["id"],
            "market_id": r["market_id"],
            "market_type": market_type,
            "strategy_name": r["strategy_name"],
            "direction": r["direction"],
            "entry_price": entry_price,
            "exit_price": (
                1.0 if raw_outcome == "win_resolution"
                else float(r["take_profit_price"] or 0) if raw_outcome == "take_profit"
                else float(r["stop_loss_price"] or 0) if raw_outcome == "stop_loss"
                else 0.0
            ),
            "bet_size_usd": bet_size,
            "shares": shares,
            "outcome": outcome,
            "raw_outcome": raw_outcome,
            "pnl": round(pnl, 6),
            "asset": asset,
            "duration_minutes": duration_minutes,
            "placed_at": r["placed_at"],
            "resolved_at": r["resolved_at"],
        })

    return trades


# ── Metrics computation ─────────────────────────────────────────────


def compute_live_metrics(trades: list[dict], strategy_name: str = "") -> dict:
    """Compute performance metrics from live trade records.

    Produces the same field set as ``engine.compute_metrics`` so reports
    are field-for-field identical between backtest and live contexts.
    """
    if not trades:
        return _empty_metrics(strategy_name)

    pnls = np.array([t["pnl"] for t in trades])
    wins = sum(1 for t in trades if t["outcome"] == "win")
    losses = sum(1 for t in trades if t["outcome"] == "loss")
    total = wins + losses

    if total == 0:
        return _empty_metrics(strategy_name)

    win_rate = wins / total * 100
    total_pnl = float(np.sum(pnls))
    avg_pnl = float(np.mean(pnls))

    # Profit factor
    winning_pnls = pnls[pnls > 0]
    losing_pnls = pnls[pnls < 0]
    sum_wins = float(np.sum(winning_pnls)) if len(winning_pnls) > 0 else 0.0
    sum_losses = float(np.abs(np.sum(losing_pnls))) if len(losing_pnls) > 0 else 0.001
    profit_factor = sum_wins / sum_losses

    # Expected value
    avg_win = float(np.mean(winning_pnls)) if len(winning_pnls) > 0 else 0.0
    avg_loss = float(np.mean(np.abs(losing_pnls))) if len(losing_pnls) > 0 else 0.0
    expected_value = (wins / total * avg_win) - (losses / total * avg_loss)

    # Risk metrics
    std_dev = float(np.std(pnls, ddof=1)) if len(pnls) > 1 else 0.001
    sharpe_ratio = avg_pnl / std_dev if std_dev > 0.0001 else 0.0

    downside_pnls = pnls[pnls < 0]
    downside_std = float(np.std(downside_pnls, ddof=1)) if len(downside_pnls) > 1 else 0.001
    sortino_ratio = avg_pnl / downside_std if downside_std > 0.0001 else 0.0

    # Max drawdown
    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

    # Robustness: per-asset profitability
    asset_pnls: dict[str, list[float]] = {}
    for t in trades:
        asset_pnls.setdefault(t["asset"], []).append(t["pnl"])
    profitable_assets = sum(1 for v in asset_pnls.values() if sum(v) > 0)
    total_assets_seen = len(asset_pnls)
    pct_profitable_assets = profitable_assets / total_assets_seen * 100 if total_assets_seen > 0 else 0

    # Robustness: per-duration profitability
    dur_pnls: dict[int, list[float]] = {}
    for t in trades:
        dur_pnls.setdefault(t["duration_minutes"], []).append(t["pnl"])
    profitable_durations = sum(1 for v in dur_pnls.values() if sum(v) > 0)
    total_durations_seen = len(dur_pnls)
    pct_profitable_durations = profitable_durations / total_durations_seen * 100 if total_durations_seen > 0 else 0

    # Consistency: 100 - stdev of per-asset win rates
    asset_wrs = []
    for v in asset_pnls.values():
        wr = sum(1 for p in v if p > 0) / len(v) * 100 if v else 0
        asset_wrs.append(wr)
    consistency_score = 100 - float(np.std(asset_wrs)) if len(asset_wrs) > 1 else 50.0
    consistency_score = max(0, min(100, consistency_score))

    # Quarters
    q_size = max(1, len(pnls) // 4)
    q_pnls = []
    for i in range(4):
        s = i * q_size
        e = s + q_size if i < 3 else len(pnls)
        q_pnls.append(float(np.sum(pnls[s:e])) if s < len(pnls) else 0.0)

    return {
        "config_id": strategy_name,
        "total_bets": total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "total_pnl": round(total_pnl, 4),
        "avg_bet_pnl": round(avg_pnl, 6),
        "profit_factor": round(profit_factor, 4),
        "expected_value": round(expected_value, 6),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "sortino_ratio": round(sortino_ratio, 4),
        "max_drawdown": round(max_drawdown, 4),
        "std_dev_pnl": round(std_dev, 6),
        "pct_profitable_assets": round(pct_profitable_assets, 1),
        "pct_profitable_durations": round(pct_profitable_durations, 1),
        "consistency_score": round(consistency_score, 2),
        "q1_pnl": round(q_pnls[0], 4),
        "q2_pnl": round(q_pnls[1], 4),
        "q3_pnl": round(q_pnls[2], 4),
        "q4_pnl": round(q_pnls[3], 4),
    }


def _empty_metrics(strategy_name: str) -> dict:
    keys = [
        "config_id", "total_bets", "wins", "losses", "win_rate_pct",
        "total_pnl", "avg_bet_pnl", "profit_factor", "expected_value",
        "sharpe_ratio", "sortino_ratio", "max_drawdown", "std_dev_pnl",
        "pct_profitable_assets", "pct_profitable_durations", "consistency_score",
        "q1_pnl", "q2_pnl", "q3_pnl", "q4_pnl",
    ]
    m = {k: 0 for k in keys}
    m["config_id"] = strategy_name
    return m


def _compute_ranking_score(metrics: dict) -> float:
    """Single-strategy ranking score (same formula as engine.add_ranking_score).

    When there's only one strategy, percentile ranking is meaningless (always 50),
    so we use raw metrics scaled to the same [0, 100] range.
    """
    # For a single strategy, use a simple weighted score of normalized metrics
    # This produces a comparable number but isn't a percentile rank
    total_pnl = metrics.get("total_pnl", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    ev = metrics.get("expected_value", 0)
    wr = metrics.get("win_rate_pct", 0)
    consistency = metrics.get("consistency_score", 0)

    # Clamp raw values to a reasonable range, then scale to [0, 100]
    # These are rough heuristics for live trading metrics
    pnl_score = min(100, max(0, 50 + total_pnl * 10))  # $0 → 50, +$5 → 100
    sharpe_score = min(100, max(0, 50 + sharpe * 25))   # 0 → 50, +2 → 100
    ev_score = min(100, max(0, 50 + ev * 100))           # $0 → 50, +$0.50 → 100
    wr_score = wr  # already 0-100

    return round(
        pnl_score * 0.30
        + ev_score * 0.25
        + sharpe_score * 0.20
        + consistency * 0.15
        + wr_score * 0.10,
        2,
    )


# ── Report generation ───────────────────────────────────────────────


async def generate_live_reports(output_dir: str = "./reports/live") -> list[StrategyReport]:
    """Query bot_trades, compute metrics per strategy, write reports.

    Returns the list of generated :class:`StrategyReport` objects.
    """
    all_trades = await _fetch_resolved_trades()

    if not all_trades:
        logger.info("[REPORT] No resolved trades found — skipping report generation")
        return []

    # Group trades by strategy_name
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for t in all_trades:
        by_strategy[t["strategy_name"]].append(t)

    # Compute date range across all trades
    placed_dates = [t["placed_at"] for t in all_trades if t.get("placed_at")]
    resolved_dates = [t["resolved_at"] for t in all_trades if t.get("resolved_at")]
    date_range_start = str(min(placed_dates)) if placed_dates else ""
    date_range_end = str(max(resolved_dates)) if resolved_dates else ""

    # Derive strategy_id from strategy_name (e.g. "S1_spike_reversion" → "S1")
    # For legacy names like "M3_spike_reversion" that haven't been remapped yet,
    # use the full name as the ID
    def _strategy_id(name: str) -> str:
        for prefix in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"):
            if name.startswith(prefix + "_") or name == prefix:
                return prefix
        return name

    reports: list[StrategyReport] = []

    for strategy_name, trades in sorted(by_strategy.items()):
        metrics = compute_live_metrics(trades, strategy_name)
        ranking_score = _compute_ranking_score(metrics)
        sid = _strategy_id(strategy_name)

        # Build trade records for the report
        trade_records = [
            {
                "market_id": t["market_id"],
                "direction": t["direction"],
                "entry_price": t["entry_price"],
                "exit_price": t["exit_price"],
                "outcome": t["outcome"],
                "pnl": t["pnl"],
                "second_entered": 0,  # not tracked in bot_trades
                "asset": t["asset"],
                "duration_minutes": t["duration_minutes"],
            }
            for t in trades
        ]

        report = StrategyReport.from_metrics(
            metrics,
            strategy_id=sid,
            strategy_name=strategy_name,
            context="live",
            total_markets=0,  # not tracked in live context
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            config={},  # live config is in bot_config table, not per-strategy
            ranking_score=ranking_score,
        )
        report.trades = trade_records

        report.to_json(os.path.join(output_dir, f"{sid}.json"))
        report.to_markdown(os.path.join(output_dir, f"{sid}.md"))
        reports.append(report)

        logger.info(
            "[REPORT] %s: %d trades, WR=%.1f%%, PnL=$%.2f, Sharpe=%.3f",
            strategy_name,
            metrics["total_bets"],
            metrics["win_rate_pct"],
            metrics["total_pnl"],
            metrics["sharpe_ratio"],
        )

    logger.info("[REPORT] Generated %d strategy report(s) in %s/", len(reports), output_dir)
    return reports


# ── CLI for manual/debug use ────────────────────────────────────────


async def _cli_main(output_dir: str) -> None:
    await init_pool()
    reports = await generate_live_reports(output_dir)
    if not reports:
        print("No resolved trades found.")
    else:
        print(f"\n=== Live Trading Reports ===")
        for r in reports:
            print(
                f"  {r.strategy_id} ({r.strategy_name}): "
                f"{r.total_bets} bets, WR={r.win_rate_pct:.1f}%, "
                f"PnL=${r.total_pnl:.4f}, Sharpe={r.sharpe_ratio:.3f}"
            )
        print(f"\nReports saved to {output_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate live trading strategy reports.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="./reports/live",
        help="Directory for reports (default: ./reports/live).",
    )
    args = parser.parse_args()
    asyncio.run(_cli_main(args.output_dir))


if __name__ == "__main__":
    main()
