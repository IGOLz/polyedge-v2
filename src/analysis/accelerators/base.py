"""Shared interfaces and helpers for accelerated strategy optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from analysis.backtest.engine import Trade


@dataclass
class PrecomputedDataset:
    """Compact market representation used by accelerated kernels."""

    strategy_id: str
    markets: list[dict]
    payload: Any
    eligible_markets: int
    skipped_markets_missing_features: int


class StrategyKernel(Protocol):
    """Contract for strategy-specific accelerated optimization kernels."""

    strategy_id: str

    def is_available(self) -> bool:
        """Return whether this kernel can run in the current environment."""

    def unavailable_reason(self) -> str:
        """Return a human-readable explanation when unavailable."""

    def prepare(
        self,
        strategy_id: str,
        markets: list[dict],
        param_grid: dict[str, list],
    ) -> PrecomputedDataset:
        """Precompute compact numeric arrays from markets for this strategy."""

    def encode_combo(self, combo: tuple[object, ...]) -> np.ndarray:
        """Encode a single parameter tuple into a numeric vector."""

    def evaluate_batch(
        self,
        dataset: PrecomputedDataset,
        encoded_batch: np.ndarray,
        combo_batch: list[tuple[object, ...]],
        param_names: list[str],
        config_id_builder,
    ) -> list[dict]:
        """Evaluate a batch of encoded parameter combinations."""

    def materialize_trades(
        self,
        dataset: PrecomputedDataset,
        param_dict: dict[str, object],
        config_id: str,
    ) -> list[Trade]:
        """Re-run one configuration and return exact trades for reporting."""


def compute_metrics_from_arrays(
    pnls: np.ndarray,
    entry_fees: np.ndarray,
    exit_fees: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    config_id: str | None = None,
) -> dict:
    """Compute backtest metrics directly from numeric arrays."""
    if pnls.size == 0:
        metrics = {key: 0 for key in (
            "config_id", "total_bets", "wins", "losses", "win_rate_pct",
            "total_pnl", "avg_bet_pnl", "profit_factor", "expected_value",
            "total_entry_fees", "total_exit_fees", "total_fees",
            "sharpe_ratio", "sortino_ratio", "max_drawdown", "std_dev_pnl",
            "pct_profitable_assets", "pct_profitable_durations", "consistency_score",
            "q1_pnl", "q2_pnl", "q3_pnl", "q4_pnl",
        )}
        metrics["config_id"] = config_id
        return metrics

    wins_mask = pnls > 0
    wins = int(np.sum(wins_mask))
    losses = int(pnls.size - wins)
    total = int(pnls.size)

    win_rate = wins / total * 100.0 if total else 0.0
    total_pnl = float(np.sum(pnls))
    avg_pnl = float(np.mean(pnls))

    winning_pnls = pnls[pnls > 0]
    losing_pnls = pnls[pnls < 0]
    sum_wins = float(np.sum(winning_pnls)) if winning_pnls.size > 0 else 0.0
    sum_losses = float(np.abs(np.sum(losing_pnls))) if losing_pnls.size > 0 else 0.001
    profit_factor = sum_wins / sum_losses

    total_entry_fees = float(np.sum(entry_fees))
    total_exit_fees = float(np.sum(exit_fees))
    total_fees = total_entry_fees + total_exit_fees

    avg_win = float(np.mean(winning_pnls)) if winning_pnls.size > 0 else 0.0
    avg_loss = float(np.mean(np.abs(losing_pnls))) if losing_pnls.size > 0 else 0.0
    expected_value = (wins / total * avg_win) - (losses / total * avg_loss)

    std_dev = float(np.std(pnls, ddof=1)) if total > 1 else 0.001
    sharpe_ratio = avg_pnl / std_dev if std_dev > 0.0001 else 0.0

    downside_pnls = pnls[pnls < 0]
    downside_std = float(np.std(downside_pnls, ddof=1)) if downside_pnls.size > 1 else 0.001
    sortino_ratio = avg_pnl / downside_std if downside_std > 0.0001 else 0.0

    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    max_drawdown = float(np.max(drawdown)) if drawdown.size > 0 else 0.0

    unique_assets = np.unique(asset_codes)
    asset_totals = []
    asset_wrs = []
    for asset_code in unique_assets:
        asset_mask = asset_codes == asset_code
        asset_pnls = pnls[asset_mask]
        asset_totals.append(float(np.sum(asset_pnls)))
        if asset_pnls.size > 0:
            asset_wrs.append(float(np.sum(asset_pnls > 0) / asset_pnls.size * 100.0))

    profitable_assets = sum(total_pnl_value > 0 for total_pnl_value in asset_totals)
    pct_profitable_assets = (
        profitable_assets / len(unique_assets) * 100.0 if unique_assets.size > 0 else 0.0
    )

    unique_durations = np.unique(duration_minutes)
    duration_totals = []
    for duration in unique_durations:
        duration_mask = duration_minutes == duration
        duration_totals.append(float(np.sum(pnls[duration_mask])))

    profitable_durations = sum(total_pnl_value > 0 for total_pnl_value in duration_totals)
    pct_profitable_durations = (
        profitable_durations / len(unique_durations) * 100.0 if unique_durations.size > 0 else 0.0
    )

    consistency_score = 100.0 - float(np.std(np.array(asset_wrs))) if len(asset_wrs) > 1 else 50.0
    consistency_score = max(0.0, min(100.0, consistency_score))

    q_size = max(1, total // 4)
    q_pnls = []
    for i in range(4):
        start = i * q_size
        end = start + q_size if i < 3 else total
        q_pnls.append(float(np.sum(pnls[start:end])) if start < total else 0.0)

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
