"""Parity tests for accelerated S25 optimizer."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis import optimize
from analysis.accelerators import get_strategy_kernel
from shared.strategies.S25 import config as s25_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S25").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


@pytest.fixture
def base_started_at():
    return datetime(2026, 3, 10, tzinfo=timezone.utc)


def _market(base_started_at, market_id: str, total_seconds: int = 100) -> dict:
    return {
        "market_id": market_id,
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": total_seconds,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "hour": 12,
        "feature_series": {},
    }


def test_s25_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(
        s25_config,
        "get_param_grid",
        lambda: {
            "checkpoint_tolerance": [2],
            "min_underlying_return_5s": [0.0006],
            "underlying_beta": [12.0],
            "min_directional_gap": [0.008],
            "min_market_delta_5s": [0.002],
            "min_trade_count": [15.0],
            "min_price_distance_from_mid": [0.05],
            "max_entry_price": [0.80],
            "stop_loss": [0.20],
            "take_profit": [0.80],
        },
    )
    m = _market(base_started_at, "s25")
    m["final_outcome"] = "Up"
    prices = np.full(m["total_seconds"], 0.50, dtype=float)
    prices[39:] = 0.74
    m["prices"] = prices
    active = np.arange(m["total_seconds"]) >= 39
    m["feature_series"] = {
        "underlying_return_5s": np.where(active, 0.0012, np.nan),
        "market_up_delta_5s": np.where(active, 0.004, np.nan),
        "underlying_trade_count": np.where(active, 20.0, np.nan),
    }

    generic_df = optimize.optimize_strategy(
        "S25",
        [m],
        str(tmp_path / "s25_generic"),
        workers=1,
        progress_interval=100,
        engine="generic",
        slippage=0.0,
    )
    accelerated_df = optimize.optimize_strategy(
        "S25",
        [m],
        str(tmp_path / "s25_accelerated"),
        workers=1,
        progress_interval=100,
        engine="accelerated",
        slippage=0.0,
    )

    assert generic_df is not None and accelerated_df is not None
    assert len(generic_df) == len(accelerated_df) == 1
    assert accelerated_df.iloc[0]["config_id"] == generic_df.iloc[0]["config_id"]
    for column in [
        "total_bets",
        "wins",
        "losses",
        "win_rate_pct",
        "total_pnl",
        "avg_bet_pnl",
        "profit_factor",
        "expected_value",
        "total_entry_fees",
        "total_exit_fees",
        "total_fees",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "std_dev_pnl",
        "pct_profitable_assets",
        "pct_profitable_durations",
        "consistency_score",
        "q1_pnl",
        "q2_pnl",
        "q3_pnl",
        "q4_pnl",
        "eligible_markets",
        "skipped_markets_missing_features",
        "ranking_score",
    ]:
        assert accelerated_df.iloc[0][column] == pytest.approx(generic_df.iloc[0][column])
