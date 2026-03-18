"""
Core backtesting engine.
Handles trade recording, fee-aware PnL calculation, and performance metrics.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

CRYPTO_FEE_RATE = 0.25
CRYPTO_FEE_EXPONENT = 2
CRYPTO_FEE_ACTIVATION_15M = datetime(2026, 1, 19, tzinfo=timezone.utc)
CRYPTO_FEE_ACTIVATION_5M = datetime(2026, 2, 12, tzinfo=timezone.utc)
CRYPTO_FEE_ACTIVATION_ALL = datetime(2026, 3, 6, tzinfo=timezone.utc)


def _market_has_crypto_fees(market) -> bool:
    """Return whether official taker fees apply to this market."""
    started_at = market.get("started_at")
    if started_at is None:
        return False

    duration = market.get("duration_minutes")
    if duration == 15:
        return started_at >= CRYPTO_FEE_ACTIVATION_15M
    if duration == 5:
        return started_at >= CRYPTO_FEE_ACTIVATION_5M
    return started_at >= CRYPTO_FEE_ACTIVATION_ALL


def polymarket_dynamic_fee(
    price: float,
    shares: float = 1.0,
    fee_rate: float = CRYPTO_FEE_RATE,
    exponent: int = CRYPTO_FEE_EXPONENT,
) -> float:
    """Calculate official Polymarket taker fee in USDC for a token trade."""
    price = max(0.0, min(1.0, price))
    if shares <= 0.0 or price <= 0.0 or price >= 1.0:
        return 0.0

    fee_usdc = shares * price * fee_rate * (price * (1.0 - price)) ** exponent
    rounded = round(fee_usdc, 4)
    return rounded if rounded >= 0.0001 else 0.0


def _trade_fee_usdc(market, token_price, shares, fee_rate_override=None):
    if not _market_has_crypto_fees(market):
        return 0.0

    fee_rate = CRYPTO_FEE_RATE if fee_rate_override is None else fee_rate_override
    return polymarket_dynamic_fee(token_price, shares=shares, fee_rate=fee_rate)


def _entry_position_after_fee(entry_price, market, fee_rate_override=None):
    """Model buying one gross share of the chosen token as a taker."""
    entry_fee_usdc = _trade_fee_usdc(
        market,
        token_price=entry_price,
        shares=1.0,
        fee_rate_override=fee_rate_override,
    )
    fee_shares = (entry_fee_usdc / entry_price) if entry_price > 0.0 else 0.0
    net_shares = max(0.0, 1.0 - fee_shares)
    entry_cost = entry_price
    return entry_cost, entry_fee_usdc, net_shares


@dataclass
class Trade:
    market_id: str
    asset: str
    duration_minutes: int
    second_entered: int
    entry_price: float      # chosen token price at entry
    direction: str          # 'Up' or 'Down'
    second_exited: int
    exit_price: float       # chosen token price at exit (1.0/0.0 at resolution)
    actual_result: str
    pnl: float
    outcome: str            # 'win' or 'loss'
    hour: int
    exit_reason: str = "resolution"
    gross_pnl: float = 0.0
    entry_fee_usdc: float = 0.0
    exit_fee_usdc: float = 0.0
    net_shares: float = 1.0


def calculate_pnl_hold(entry_price, direction, actual_result, market, fee_rate_override=None):
    """PnL for hold-to-resolution with official Polymarket fee handling."""
    entry_cost, entry_fee_usdc, net_shares = _entry_position_after_fee(
        entry_price,
        market,
        fee_rate_override=fee_rate_override,
    )
    won = direction == actual_result
    if won:
        gross_pnl = 1.0 - entry_price
        payout = net_shares
        pnl = payout - entry_cost
        return pnl, gross_pnl, entry_fee_usdc, 0.0, net_shares

    return -entry_cost, -entry_price, entry_fee_usdc, 0.0, net_shares


def calculate_pnl_exit(entry_price, exit_price, market, fee_rate_override=None):
    """PnL for early exit using token-side prices for the chosen outcome token."""
    entry_cost, entry_fee_usdc, net_shares = _entry_position_after_fee(
        entry_price,
        market,
        fee_rate_override=fee_rate_override,
    )
    gross_pnl = exit_price - entry_price
    gross_proceeds = net_shares * exit_price
    exit_fee_usdc = _trade_fee_usdc(
        market,
        token_price=exit_price,
        shares=net_shares,
        fee_rate_override=fee_rate_override,
    )
    pnl = gross_proceeds - exit_fee_usdc - entry_cost
    return pnl, gross_pnl, entry_fee_usdc, exit_fee_usdc, net_shares


def simulate_sl_tp_exit(
    prices: np.ndarray,
    entry_second: int,
    entry_price: float,
    direction: str,
    stop_loss: float,
    take_profit: float,
) -> tuple[int, float | None, str]:
    """Simulate stop-loss / take-profit exits using token-side thresholds."""
    for second in range(entry_second + 1, len(prices)):
        up_price = prices[second]
        if np.isnan(up_price):
            continue

        token_price = float(up_price) if direction == "Up" else float(1.0 - up_price)
        if token_price <= stop_loss:
            return second, token_price, "sl"
        if token_price >= take_profit:
            return second, token_price, "tp"

    return -1, None, "resolution"


def make_trade(
    market,
    second_entered,
    entry_price,
    direction,
    second_exited=-1,
    exit_price=None,
    slippage=0.0,
    base_rate=None,
    *,
    stop_loss=None,
    take_profit=None,
):
    """Create a Trade with fee-aware PnL.

    ``entry_price`` is the token-side price for the chosen direction:
      - Up trade: yes-token price
      - Down trade: no-token price

    ``base_rate`` is kept for compatibility and acts as an optional fee-rate
    override. When omitted, official market-aware Polymarket crypto fees are
    used automatically.
    """
    actual = market["final_outcome"]
    adjusted_entry = max(0.01, min(0.99, entry_price + slippage))

    exit_reason = "resolution"
    gross_pnl = 0.0
    entry_fee_usdc = 0.0
    exit_fee_usdc = 0.0
    net_shares = 1.0

    if stop_loss is not None and take_profit is not None:
        prices = market.get("prices")
        if prices is not None:
            sim_exit_second, sim_exit_price, exit_reason = simulate_sl_tp_exit(
                prices,
                second_entered,
                adjusted_entry,
                direction,
                stop_loss,
                take_profit,
            )
            if exit_reason in {"sl", "tp"}:
                second_exited = sim_exit_second
                exit_price = sim_exit_price
                pnl, gross_pnl, entry_fee_usdc, exit_fee_usdc, net_shares = calculate_pnl_exit(
                    adjusted_entry,
                    exit_price,
                    market,
                    fee_rate_override=base_rate,
                )
                outcome = "win" if pnl > 0 else "loss"
            else:
                pnl, gross_pnl, entry_fee_usdc, exit_fee_usdc, net_shares = calculate_pnl_hold(
                    adjusted_entry,
                    direction,
                    actual,
                    market,
                    fee_rate_override=base_rate,
                )
                outcome = "win" if direction == actual else "loss"
                second_exited = market["total_seconds"] - 1
                exit_price = 1.0 if outcome == "win" else 0.0
        else:
            pnl, gross_pnl, entry_fee_usdc, exit_fee_usdc, net_shares = calculate_pnl_hold(
                adjusted_entry,
                direction,
                actual,
                market,
                fee_rate_override=base_rate,
            )
            outcome = "win" if direction == actual else "loss"
            second_exited = market["total_seconds"] - 1
            exit_price = 1.0 if outcome == "win" else 0.0
    else:
        pnl, gross_pnl, entry_fee_usdc, exit_fee_usdc, net_shares = calculate_pnl_hold(
            adjusted_entry,
            direction,
            actual,
            market,
            fee_rate_override=base_rate,
        )
        outcome = "win" if direction == actual else "loss"
        second_exited = market["total_seconds"] - 1
        exit_price = 1.0 if outcome == "win" else 0.0

    return Trade(
        market_id=market["market_id"],
        asset=market["asset"],
        duration_minutes=market["duration_minutes"],
        second_entered=second_entered,
        entry_price=round(adjusted_entry, 4),
        direction=direction,
        second_exited=second_exited,
        exit_price=round(exit_price, 4),
        actual_result=actual,
        pnl=round(pnl, 6),
        outcome=outcome,
        hour=market["hour"],
        exit_reason=exit_reason,
        gross_pnl=round(gross_pnl, 6),
        entry_fee_usdc=round(entry_fee_usdc, 6),
        exit_fee_usdc=round(exit_fee_usdc, 6),
        net_shares=round(net_shares, 6),
    )


def compute_metrics(trades, config_id=None):
    """Compute all performance metrics for a list of trades."""
    if not trades:
        return _empty_metrics(config_id)

    pnls = np.array([t.pnl for t in trades])
    wins = sum(1 for t in trades if t.outcome == "win")
    losses = sum(1 for t in trades if t.outcome == "loss")
    total = wins + losses

    if total == 0:
        return _empty_metrics(config_id)

    win_rate = wins / total * 100
    total_pnl = float(np.sum(pnls))
    avg_pnl = float(np.mean(pnls))

    winning_pnls = pnls[pnls > 0]
    losing_pnls = pnls[pnls < 0]
    sum_wins = float(np.sum(winning_pnls)) if len(winning_pnls) > 0 else 0.0
    sum_losses = float(np.abs(np.sum(losing_pnls))) if len(losing_pnls) > 0 else 0.001
    profit_factor = sum_wins / sum_losses
    total_entry_fees = float(sum(t.entry_fee_usdc for t in trades))
    total_exit_fees = float(sum(t.exit_fee_usdc for t in trades))
    total_fees = total_entry_fees + total_exit_fees

    avg_win = float(np.mean(winning_pnls)) if len(winning_pnls) > 0 else 0.0
    avg_loss = float(np.mean(np.abs(losing_pnls))) if len(losing_pnls) > 0 else 0.0
    expected_value = (wins / total * avg_win) - (losses / total * avg_loss)

    std_dev = float(np.std(pnls, ddof=1)) if len(pnls) > 1 else 0.001
    sharpe_ratio = avg_pnl / std_dev if std_dev > 0.0001 else 0.0

    downside_pnls = pnls[pnls < 0]
    downside_std = float(np.std(downside_pnls, ddof=1)) if len(downside_pnls) > 1 else 0.001
    sortino_ratio = avg_pnl / downside_std if downside_std > 0.0001 else 0.0

    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

    asset_pnls = {}
    for t in trades:
        asset_pnls.setdefault(t.asset, []).append(t.pnl)
    profitable_assets = sum(1 for values in asset_pnls.values() if sum(values) > 0)
    total_assets_seen = len(asset_pnls)
    pct_profitable_assets = (
        profitable_assets / total_assets_seen * 100 if total_assets_seen > 0 else 0
    )

    dur_pnls = {}
    for t in trades:
        dur_pnls.setdefault(t.duration_minutes, []).append(t.pnl)
    profitable_durations = sum(1 for values in dur_pnls.values() if sum(values) > 0)
    total_durations_seen = len(dur_pnls)
    pct_profitable_durations = (
        profitable_durations / total_durations_seen * 100
        if total_durations_seen > 0
        else 0
    )

    asset_wrs = []
    for values in asset_pnls.values():
        wr = sum(1 for pnl in values if pnl > 0) / len(values) * 100 if values else 0
        asset_wrs.append(wr)
    consistency_score = 100 - float(np.std(asset_wrs)) if len(asset_wrs) > 1 else 50.0
    consistency_score = max(0, min(100, consistency_score))

    q_size = max(1, len(pnls) // 4)
    q_pnls = []
    for i in range(4):
        start = i * q_size
        end = start + q_size if i < 3 else len(pnls)
        q_pnls.append(float(np.sum(pnls[start:end])) if start < len(pnls) else 0.0)

    return {
        "config_id": config_id,
        "total_bets": total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "total_pnl": round(total_pnl, 4),
        "avg_bet_pnl": round(avg_pnl, 6),
        "profit_factor": round(profit_factor, 4),
        "expected_value": round(expected_value, 6),
        "total_entry_fees": round(total_entry_fees, 6),
        "total_exit_fees": round(total_exit_fees, 6),
        "total_fees": round(total_fees, 6),
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


def _empty_metrics(config_id):
    keys = [
        "config_id", "total_bets", "wins", "losses", "win_rate_pct",
        "total_pnl", "avg_bet_pnl", "profit_factor", "expected_value",
        "total_entry_fees", "total_exit_fees", "total_fees",
        "sharpe_ratio", "sortino_ratio", "max_drawdown", "std_dev_pnl",
        "pct_profitable_assets", "pct_profitable_durations", "consistency_score",
        "q1_pnl", "q2_pnl", "q3_pnl", "q4_pnl",
    ]
    metrics = {key: 0 for key in keys}
    metrics["config_id"] = config_id
    return metrics


def add_ranking_score(df):
    """Add composite ranking score to results DataFrame."""
    if df.empty:
        df["ranking_score"] = []
        return df

    df = df.copy()
    for col in ["total_pnl", "sharpe_ratio", "expected_value", "win_rate_pct"]:
        if df[col].std() > 0:
            df[f"{col}_pctile"] = df[col].rank(pct=True) * 100
        else:
            df[f"{col}_pctile"] = 50.0

    df["ranking_score"] = (
        df["total_pnl_pctile"] * 0.30 +
        df["expected_value_pctile"] * 0.25 +
        df["sharpe_ratio_pctile"] * 0.20 +
        df["consistency_score"] * 0.15 +
        df["win_rate_pct_pctile"] * 0.10
    ).round(2)

    df.drop(columns=[col for col in df.columns if col.endswith("_pctile")], inplace=True)
    return df


def save_module_results(results_df, trades_by_config, module_name, module_dir, top_n=10):
    """Save CSV results, best configs text, analysis markdown, and sample trades."""
    os.makedirs(module_dir, exist_ok=True)

    if results_df.empty:
        with open(os.path.join(module_dir, f"{module_name}_Analysis.md"), "w") as handle:
            handle.write(f"# {module_name} Analysis\n\nNo results produced.\n")
        return results_df

    results_df = results_df.sort_values("ranking_score", ascending=False).reset_index(drop=True)

    csv_path = os.path.join(module_dir, f"Test_{module_name}_Results.csv")
    results_df.to_csv(csv_path, index=False)
    print(f"  Saved {csv_path}")

    best_path = os.path.join(module_dir, f"{module_name}_Best_Configs.txt")
    with open(best_path, "w") as handle:
        handle.write(f"TOP {top_n} CONFIGURATIONS - {module_name}\n")
        handle.write("=" * 100 + "\n\n")
        for idx, row in results_df.head(top_n).iterrows():
            handle.write(f"Rank {idx + 1}:\n")
            for col in results_df.columns:
                handle.write(f"  {col}: {row[col]}\n")
            handle.write("\n")
            cid = row.get("config_id")
            if cid and cid in trades_by_config:
                samples = trades_by_config[cid][:20]
                if samples:
                    handle.write("  Sample trades:\n")
                    for trade in samples:
                        handle.write(
                            f"    {trade.market_id[:16]}.. s={trade.second_entered:>3} "
                            f"dir={trade.direction:<4} entry={trade.entry_price:.3f} "
                            f"res={trade.actual_result:<4} pnl={trade.pnl:+.4f}\n"
                        )
                    handle.write("\n")
    print(f"  Saved {best_path}")

    analysis_path = os.path.join(module_dir, f"{module_name}_Analysis.md")
    valid = results_df[results_df["total_bets"] > 0]
    profitable = valid[valid["total_pnl"] > 0]

    with open(analysis_path, "w") as handle:
        handle.write(f"# {module_name} Analysis\n\n")
        handle.write("## Summary\n\n")
        handle.write(f"- Configurations tested: {len(results_df)}\n")
        handle.write(f"- With trades: {len(valid)}\n")
        handle.write(f"- Profitable: {len(profitable)}\n")
        handle.write(f"- Unprofitable: {len(valid) - len(profitable)}\n\n")

        if not valid.empty:
            best = results_df.iloc[0]
            handle.write("## Best Configuration (by ranking score)\n\n")
            handle.write("| Metric | Value |\n|--------|-------|\n")
            for col in results_df.columns:
                handle.write(f"| {col} | {best[col]} |\n")
            handle.write("\n")

            handle.write("## Metrics Distribution (configs with trades)\n\n")
            handle.write("| Metric | Mean | Std | Min | Max |\n")
            handle.write("|--------|------|-----|-----|-----|\n")
            for col in [
                "win_rate_pct",
                "total_pnl",
                "avg_bet_pnl",
                "sharpe_ratio",
                "profit_factor",
                "max_drawdown",
                "consistency_score",
            ]:
                if col in valid.columns:
                    handle.write(
                        f"| {col} | {valid[col].mean():.4f} | {valid[col].std():.4f} "
                        f"| {valid[col].min():.4f} | {valid[col].max():.4f} |\n"
                    )

    print(f"  Saved {analysis_path}")
    return results_df


def save_trade_log(trades, filepath):
    """Save a list of Trade objects to CSV."""
    if not trades:
        return

    rows = []
    for trade in trades:
        rows.append(
            {
                "market_id": trade.market_id,
                "asset": trade.asset,
                "duration_minutes": trade.duration_minutes,
                "second_entered": trade.second_entered,
                "entry_price": trade.entry_price,
                "direction": trade.direction,
                "second_exited": trade.second_exited,
                "exit_price": trade.exit_price,
                "actual_result": trade.actual_result,
                "pnl": trade.pnl,
                "outcome": trade.outcome,
                "hour": trade.hour,
                "exit_reason": trade.exit_reason,
                "gross_pnl": trade.gross_pnl,
                "entry_fee_usdc": trade.entry_fee_usdc,
                "exit_fee_usdc": trade.exit_fee_usdc,
                "net_shares": trade.net_shares,
            }
        )
    pd.DataFrame(rows).to_csv(filepath, index=False)
