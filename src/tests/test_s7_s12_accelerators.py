"""Parity tests for accelerated S7-S12 optimizers."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis import optimize
from analysis.accelerators import get_strategy_kernel
from shared.strategies.S7 import config as s7_config
from shared.strategies.S8 import config as s8_config
from shared.strategies.S9 import config as s9_config
from shared.strategies.S10 import config as s10_config
from shared.strategies.S11 import config as s11_config
from shared.strategies.S12 import config as s12_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S7").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


def _assert_parity(strategy_id: str, markets: list[dict], tmp_path) -> None:
    generic_df = optimize.optimize_strategy(
        strategy_id=strategy_id,
        markets=markets,
        output_dir=str(tmp_path / f"{strategy_id.lower()}_generic"),
        workers=1,
        progress_interval=100,
        engine="generic",
        slippage=0.0,
    )
    accelerated_df = optimize.optimize_strategy(
        strategy_id=strategy_id,
        markets=markets,
        output_dir=str(tmp_path / f"{strategy_id.lower()}_accelerated"),
        workers=1,
        progress_interval=100,
        engine="accelerated",
        slippage=0.0,
    )

    assert generic_df is not None and accelerated_df is not None
    assert len(generic_df) == len(accelerated_df) == 1
    assert accelerated_df.iloc[0]["config_id"] == generic_df.iloc[0]["config_id"]
    for column in [
        "total_bets", "wins", "losses", "win_rate_pct", "total_pnl", "avg_bet_pnl",
        "profit_factor", "expected_value", "total_entry_fees", "total_exit_fees",
        "total_fees", "sharpe_ratio", "sortino_ratio", "max_drawdown", "std_dev_pnl",
        "pct_profitable_assets", "pct_profitable_durations", "consistency_score",
        "q1_pnl", "q2_pnl", "q3_pnl", "q4_pnl", "eligible_markets",
        "skipped_markets_missing_features", "ranking_score",
    ]:
        assert accelerated_df.iloc[0][column] == pytest.approx(generic_df.iloc[0][column])


@pytest.fixture
def base_started_at():
    return datetime(2026, 3, 10, tzinfo=timezone.utc)


def test_s7_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s7_config, "get_param_grid", lambda: {
        "min_agreement": [2],
        "calibration_enabled": [True],
        "momentum_enabled": [True],
        "volatility_enabled": [False],
        "calibration_min_deviation": [0.06],
        "calibration_rebound_min_move": [0.02],
        "momentum_threshold": [0.08],
        "momentum_efficiency_min": [0.80],
        "volatility_threshold": [0.02],
        "volatility_reversal_min_move": [0.01],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [
        {
            "market_id": "s7_up",
            "market_type": "btc_5m",
            "asset": "btc",
            "duration_minutes": 5,
            "total_seconds": 10,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Up",
            "hour": 12,
            "prices": np.array([0.35, 0.38, 0.41, 0.45, 0.50, 0.56, 0.62, 0.66, 0.70, 0.74], dtype=float),
            "feature_series": {},
        },
        {
            "market_id": "s7_none",
            "market_type": "eth_5m",
            "asset": "eth",
            "duration_minutes": 5,
            "total_seconds": 10,
            "started_at": base_started_at,
            "ended_at": base_started_at,
            "final_outcome": "Down",
            "hour": 13,
            "prices": np.array([0.50, 0.49, 0.50, 0.49, 0.50, 0.49, 0.50, 0.49, 0.50, 0.49], dtype=float),
            "feature_series": {},
        },
    ]
    _assert_parity("S7", markets, tmp_path)


def test_s8_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s8_config, "get_param_grid", lambda: {
        "setup_window_end": [3],
        "breakout_scan_start": [4],
        "breakout_scan_end": [7],
        "breakout_buffer": [0.01],
        "min_range_width": [0.02],
        "max_range_width": [0.20],
        "confirmation_points": [2],
        "min_distance_from_mid": [0.03],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [{
        "market_id": "s8_up",
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": 8,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "final_outcome": "Up",
        "hour": 12,
        "prices": np.array([0.48, 0.49, 0.50, 0.51, 0.54, 0.56, 0.58, 0.60], dtype=float),
        "feature_series": {},
    }]
    _assert_parity("S8", markets, tmp_path)


def test_s9_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s9_config, "get_param_grid", lambda: {
        "compression_window": [3],
        "compression_max_std": [0.02],
        "compression_max_range": [0.04],
        "trigger_scan_start": [4],
        "trigger_scan_end": [7],
        "breakout_distance": [0.03],
        "momentum_lookback": [3],
        "efficiency_min": [0.70],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [{
        "market_id": "s9_up",
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": 8,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "final_outcome": "Up",
        "hour": 12,
        "prices": np.array([0.49, 0.50, 0.50, 0.50, 0.54, 0.58, 0.62, 0.66], dtype=float),
        "feature_series": {},
    }]
    _assert_parity("S9", markets, tmp_path)


def test_s10_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s10_config, "get_param_grid", lambda: {
        "impulse_start": [0],
        "impulse_end": [3],
        "impulse_threshold": [0.08],
        "retrace_window": [3],
        "retrace_min": [0.10],
        "retrace_max": [0.60],
        "reacceleration_threshold": [0.02],
        "impulse_efficiency_min": [0.70],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [{
        "market_id": "s10_up",
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": 8,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "final_outcome": "Up",
        "hour": 12,
        "prices": np.array([0.40, 0.46, 0.52, 0.58, 0.55, 0.57, 0.60, 0.64], dtype=float),
        "feature_series": {},
    }]
    _assert_parity("S10", markets, tmp_path)


def test_s11_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s11_config, "get_param_grid", lambda: {
        "precondition_window": [3],
        "extreme_deviation": [0.08],
        "reclaim_scan_start": [4],
        "reclaim_scan_end": [7],
        "hold_seconds": [2],
        "hold_buffer": [0.01],
        "post_reclaim_move": [0.02],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [{
        "market_id": "s11_up",
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": 8,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "final_outcome": "Up",
        "hour": 12,
        "prices": np.array([0.38, 0.40, 0.42, 0.55, 0.57, 0.60, 0.62, 0.64], dtype=float),
        "feature_series": {},
    }]
    _assert_parity("S11", markets, tmp_path)


def test_s12_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s12_config, "get_param_grid", lambda: {
        "late_phase_start_pct": [0.50],
        "lookback_seconds": [3],
        "net_move_threshold": [0.06],
        "efficiency_min": [0.70],
        "max_flip_count": [1],
        "min_price_distance_from_mid": [0.03],
        "min_remaining_seconds": [1],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })
    markets = [{
        "market_id": "s12_up",
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": 8,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "final_outcome": "Up",
        "hour": 12,
        "prices": np.array([0.45, 0.47, 0.50, 0.54, 0.58, 0.62, 0.66, 0.70], dtype=float),
        "feature_series": {},
    }]
    _assert_parity("S12", markets, tmp_path)
