"""Parity and precompute tests for the accelerated S1 optimizer."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis import optimize
from analysis.accelerators import get_strategy_kernel
from shared.strategies import helpers
from shared.strategies.S1 import config as s1_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S1").is_available(),
    reason="Numba-backed S1 accelerator is not available in this environment.",
)


@pytest.fixture
def synthetic_markets():
    started_at = datetime(2026, 3, 10, tzinfo=timezone.utc)
    return [
        {
            "market_id": "m1",
            "market_type": "btc_5m",
            "asset": "btc",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": started_at,
            "ended_at": started_at,
            "final_outcome": "Up",
            "hour": 12,
            "prices": np.array([0.52, np.nan, 0.39, 0.41, 0.44, 0.46, 0.48, 0.49], dtype=float),
            "feature_series": {},
        },
        {
            "market_id": "m2",
            "market_type": "eth_5m",
            "asset": "eth",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": started_at,
            "ended_at": started_at,
            "final_outcome": "Down",
            "hour": 13,
            "prices": np.array([0.48, 0.61, 0.63, np.nan, 0.60, 0.57, 0.55, 0.54], dtype=float),
            "feature_series": {},
        },
        {
            "market_id": "m3",
            "market_type": "sol_5m",
            "asset": "sol",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": started_at,
            "ended_at": started_at,
            "final_outcome": "Down",
            "hour": 14,
            "prices": np.array([0.50, 0.49, 0.48, 0.47, 0.46, 0.45, 0.44, 0.43], dtype=float),
            "feature_series": {},
        },
        {
            "market_id": "m4",
            "market_type": "xrp_5m",
            "asset": "xrp",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": started_at,
            "ended_at": started_at,
            "final_outcome": "Up",
            "hour": 15,
            "prices": np.array([0.47, 0.60, 0.64, 0.62, 0.61, 0.59, 0.58, 0.57], dtype=float),
            "feature_series": {},
        },
    ]


@pytest.fixture
def small_s1_grid(monkeypatch):
    grid = {
        "entry_window_start": [1],
        "entry_window_end": [5],
        "price_low_threshold": [0.42],
        "price_high_threshold": [0.60],
        "min_deviation": [0.06],
        "rebound_lookback": [3],
        "rebound_min_move": [0.02],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    }
    monkeypatch.setattr(s1_config, "get_param_grid", lambda: grid)
    return grid


def test_s1_precompute_matches_helper_behavior(synthetic_markets, small_s1_grid):
    kernel = get_strategy_kernel("S1")
    dataset = kernel.prepare("S1", synthetic_markets, small_s1_grid)
    payload = dataset.payload

    for market_idx, market in enumerate(synthetic_markets):
        prices = market["prices"]
        for sec in range(market["total_seconds"]):
            expected_price = helpers.get_price(prices, sec, tolerance=2)
            actual_price = payload.nearest_prices[market_idx, sec]
            if expected_price is None:
                assert np.isnan(actual_price)
            else:
                assert actual_price == pytest.approx(expected_price)

            expected_move = helpers.trailing_net_move(prices, sec, 3)
            actual_move = payload.trailing_moves[0, market_idx, sec]
            if expected_move is None:
                assert np.isnan(actual_move)
            else:
                assert actual_move == pytest.approx(expected_move)


def test_accelerated_optimizer_matches_generic_for_s1(tmp_path, synthetic_markets, small_s1_grid):
    generic_output = tmp_path / "generic"
    accelerated_output = tmp_path / "accelerated"

    generic_df = optimize.optimize_strategy(
        strategy_id="S1",
        markets=synthetic_markets,
        output_dir=str(generic_output),
        workers=1,
        progress_interval=100,
        engine="generic",
        slippage=0.0,
    )
    accelerated_df = optimize.optimize_strategy(
        strategy_id="S1",
        markets=synthetic_markets,
        output_dir=str(accelerated_output),
        workers=1,
        progress_interval=100,
        engine="accelerated",
        slippage=0.0,
    )

    assert generic_df is not None
    assert accelerated_df is not None
    assert len(generic_df) == 1
    assert len(accelerated_df) == 1

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

    accelerated_run_dirs = sorted((accelerated_output / "S1").glob("run_*"))
    assert len(accelerated_run_dirs) == 1
    run_dir = accelerated_run_dirs[0]

    assert (run_dir / "Test_optimize_S1_Results.csv").exists()
    assert (run_dir / "optimize_S1_Best_Configs.txt").exists()
    assert (run_dir / "optimize_S1_Analysis.md").exists()
