"""Parity tests for accelerated S2-S6 optimizers."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis import optimize
from analysis.accelerators import get_strategy_kernel
from shared.strategies.S2 import config as s2_config
from shared.strategies.S3 import config as s3_config
from shared.strategies.S4 import config as s4_config
from shared.strategies.S5 import config as s5_config
from shared.strategies.S6 import config as s6_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S2").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


def _run_parity(strategy_id: str, markets: list[dict], tmp_path, grid_patch) -> None:
    generic_df = optimize.optimize_strategy(
        strategy_id=strategy_id,
        markets=markets,
        output_dir=str(tmp_path / f"{strategy_id.lower()}_generic"),
        workers=1,
        progress_interval=100,
        engine="generic",
    )
    accelerated_df = optimize.optimize_strategy(
        strategy_id=strategy_id,
        markets=markets,
        output_dir=str(tmp_path / f"{strategy_id.lower()}_accelerated"),
        workers=1,
        progress_interval=100,
        engine="accelerated",
    )

    assert generic_df is not None
    assert accelerated_df is not None
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


@pytest.fixture
def base_started_at():
    return datetime(2026, 3, 10, tzinfo=timezone.utc)


def test_s2_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s2_config, "get_param_grid", lambda: {
        "eval_window_start": [1],
        "eval_window_end": [4],
        "momentum_threshold": [0.10],
        "tolerance": [2],
        "max_entry_second": [6],
        "efficiency_min": [0.80],
        "min_distance_from_mid": [0.03],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [
        {
            "market_id": "s2_up",
            "market_type": "btc_5m",
            "asset": "btc",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Up",
            "hour": 12,
            "prices": np.array([0.40, 0.43, 0.47, 0.52, 0.58, 0.62, 0.66, 0.69], dtype=float),
            "feature_series": {},
        },
        {
            "market_id": "s2_none",
            "market_type": "eth_5m",
            "asset": "eth",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Down",
            "hour": 13,
            "prices": np.array([0.49, 0.50, 0.51, 0.50, 0.49, 0.50, 0.49, 0.50], dtype=float),
            "feature_series": {},
        },
    ]
    _run_parity("S2", markets, tmp_path, s2_config.get_param_grid)


def test_s3_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s3_config, "get_param_grid", lambda: {
        "spike_threshold": [0.75],
        "spike_lookback": [3],
        "reversion_pct": [0.10],
        "min_reversion_sec": [2],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [
        {
            "market_id": "s3_down",
            "market_type": "btc_5m",
            "asset": "btc",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Down",
            "hour": 12,
            "prices": np.array([0.52, 0.60, 0.82, 0.78, 0.72, 0.68, 0.63, 0.59], dtype=float),
            "feature_series": {},
        },
        {
            "market_id": "s3_up",
            "market_type": "eth_5m",
            "asset": "eth",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Up",
            "hour": 13,
            "prices": np.array([0.48, 0.35, 0.18, 0.22, 0.27, 0.33, 0.40, 0.45], dtype=float),
            "feature_series": {},
        },
    ]
    _run_parity("S3", markets, tmp_path, s3_config.get_param_grid)


def test_s4_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s4_config, "get_param_grid", lambda: {
        "lookback_window": [6],
        "vol_threshold": [0.03],
        "eval_second": [6],
        "extreme_price_low": [0.35],
        "extreme_price_high": [0.65],
        "reversal_lookback": [3],
        "reversal_min_move": [0.03],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [
        {
            "market_id": "s4_up",
            "market_type": "btc_5m",
            "asset": "btc",
            "duration_minutes": 5,
            "total_seconds": 10,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Up",
            "hour": 12,
            "prices": np.array([0.50, 0.42, 0.30, 0.38, 0.29, 0.34, 0.40, 0.48, 0.55, 0.60], dtype=float),
            "feature_series": {},
        },
        {
            "market_id": "s4_down",
            "market_type": "eth_5m",
            "asset": "eth",
            "duration_minutes": 5,
            "total_seconds": 10,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Down",
            "hour": 13,
            "prices": np.array([0.50, 0.58, 0.72, 0.64, 0.75, 0.69, 0.63, 0.57, 0.53, 0.49], dtype=float),
            "feature_series": {},
        },
    ]
    _run_parity("S4", markets, tmp_path, s4_config.get_param_grid)


def test_s5_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s5_config, "get_param_grid", lambda: {
        "entry_window_start": [2],
        "entry_window_end": [6],
        "allowed_hours": [[13, 14, 15, 16, 17, 18]],
        "price_range_low": [0.48],
        "price_range_high": [0.60],
        "approach_lookback": [2],
        "cross_buffer": [0.01],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [
        {
            "market_id": "s5_up",
            "market_type": "btc_5m",
            "asset": "btc",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Up",
            "hour": 13,
            "prices": np.array([0.44, 0.47, 0.49, 0.52, 0.55, 0.58, 0.60, 0.62], dtype=float),
            "feature_series": {},
        },
        {
            "market_id": "s5_filtered",
            "market_type": "eth_5m",
            "asset": "eth",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Down",
            "hour": 8,
            "prices": np.array([0.56, 0.53, 0.51, 0.48, 0.45, 0.42, 0.40, 0.38], dtype=float),
            "feature_series": {},
        },
    ]
    _run_parity("S5", markets, tmp_path, s5_config.get_param_grid)


def test_s6_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s6_config, "get_param_grid", lambda: {
        "streak_length": [3],
        "streak_direction_filter": ["Up"],
        "entry_window_start": [1],
        "entry_window_end": [5],
        "price_floor": [0.20],
        "price_ceiling": [0.80],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [
        {
            "market_id": "s6_down",
            "market_type": "btc_5m",
            "asset": "btc",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Down",
            "hour": 12,
            "prices": np.array([0.55, 0.58, 0.61, 0.60, 0.59, 0.57, 0.54, 0.51], dtype=float),
            "feature_series": {},
            "prior_market_type_streak_direction": "Up",
            "prior_market_type_streak_length": 4,
        },
        {
            "market_id": "s6_skip",
            "market_type": "eth_5m",
            "asset": "eth",
            "duration_minutes": 5,
            "total_seconds": 8,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Up",
            "hour": 13,
            "prices": np.array([0.45, 0.44, 0.43, 0.42, 0.41, 0.40, 0.39, 0.38], dtype=float),
            "feature_series": {},
            "prior_market_type_streak_direction": "Down",
            "prior_market_type_streak_length": 2,
        },
    ]
    _run_parity("S6", markets, tmp_path, s6_config.get_param_grid)
