"""Parity tests for accelerated S13-S19 optimizers."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis import optimize
from analysis.accelerators import get_strategy_kernel
from shared.strategies.S13 import config as s13_config
from shared.strategies.S14 import config as s14_config
from shared.strategies.S15 import config as s15_config
from shared.strategies.S16 import config as s16_config
from shared.strategies.S17 import config as s17_config
from shared.strategies.S18 import config as s18_config
from shared.strategies.S19 import config as s19_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S13").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


def _assert_parity(strategy_id: str, markets: list[dict], tmp_path) -> None:
    generic_df = optimize.optimize_strategy(strategy_id, markets, str(tmp_path / f"{strategy_id.lower()}_generic"), workers=1, progress_interval=100, engine="generic", slippage=0.0)
    accelerated_df = optimize.optimize_strategy(strategy_id, markets, str(tmp_path / f"{strategy_id.lower()}_accelerated"), workers=1, progress_interval=100, engine="accelerated", slippage=0.0)
    assert generic_df is not None and accelerated_df is not None
    assert len(generic_df) == len(accelerated_df) == 1
    assert accelerated_df.iloc[0]["config_id"] == generic_df.iloc[0]["config_id"]
    for column in [
        "total_bets", "wins", "losses", "win_rate_pct", "total_pnl", "avg_bet_pnl",
        "profit_factor", "expected_value", "total_entry_fees", "total_exit_fees", "total_fees",
        "sharpe_ratio", "sortino_ratio", "max_drawdown", "std_dev_pnl",
        "pct_profitable_assets", "pct_profitable_durations", "consistency_score",
        "q1_pnl", "q2_pnl", "q3_pnl", "q4_pnl", "eligible_markets",
        "skipped_markets_missing_features", "ranking_score",
    ]:
        assert accelerated_df.iloc[0][column] == pytest.approx(generic_df.iloc[0][column])


@pytest.fixture
def base_started_at():
    return datetime(2026, 3, 10, tzinfo=timezone.utc)


def _base_market(base_started_at, market_id: str, asset: str = "btc"):
    return {
        "market_id": market_id,
        "market_type": f"{asset}_5m",
        "asset": asset,
        "duration_minutes": 5,
        "total_seconds": 8,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "hour": 12,
        "feature_series": {},
    }


def test_s13_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s13_config, "get_param_grid", lambda: {
        "feature_window": [5], "entry_window_start": [1], "entry_window_end": [6],
        "min_underlying_return": [0.001], "min_market_confirmation": [0.002], "max_market_delta": [0.05],
        "max_price_distance_from_mid": [0.20], "max_underlying_vol": [0.02], "stop_loss": [0.20], "take_profit": [0.80],
    })
    m = _base_market(base_started_at, "s13")
    m["final_outcome"] = "Up"
    m["prices"] = np.array([0.48, 0.52, 0.54, 0.57, 0.60, 0.63, 0.66, 0.70], dtype=float)
    m["feature_series"] = {
        "underlying_return_5s": np.array([np.nan, 0.002, 0.002, 0.003, 0.003, 0.004, 0.004, 0.004], dtype=float),
        "market_up_delta_5s": np.array([np.nan, 0.003, 0.004, 0.005, 0.006, 0.006, 0.006, 0.006], dtype=float),
        "underlying_realized_vol_10s": np.array([0.005] * 8, dtype=float),
    }
    _assert_parity("S13", [m], tmp_path)


def test_s14_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s14_config, "get_param_grid", lambda: {
        "feature_window": [5], "entry_window_start": [1], "entry_window_end": [6],
        "min_market_delta_abs": [0.03], "max_underlying_return_abs": [0.001], "extreme_price_low": [0.25], "extreme_price_high": [0.65],
        "require_direction_mismatch": [True], "stop_loss": [0.20], "take_profit": [0.80],
    })
    m = _base_market(base_started_at, "s14")
    m["final_outcome"] = "Down"
    m["prices"] = np.array([0.60, 0.66, 0.70, 0.72, 0.69, 0.64, 0.58, 0.52], dtype=float)
    m["feature_series"] = {
        "underlying_return_5s": np.array([0.0] * 8, dtype=float),
        "market_up_delta_5s": np.array([0.04] * 8, dtype=float),
        "direction_mismatch_5s": np.array([1.0] * 8, dtype=float),
    }
    _assert_parity("S14", [m], tmp_path)


def test_s15_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s15_config, "get_param_grid", lambda: {
        "setup_window_end": [2], "breakout_scan_start": [3], "breakout_scan_end": [6], "breakout_buffer": [0.01],
        "confirmation_points": [1], "feature_window": [5], "min_underlying_return": [0.001], "min_trade_count": [5.0],
        "stop_loss": [0.20], "take_profit": [0.80],
    })
    m = _base_market(base_started_at, "s15")
    m["final_outcome"] = "Up"
    m["prices"] = np.array([0.48, 0.49, 0.50, 0.54, 0.57, 0.60, 0.64, 0.68], dtype=float)
    m["feature_series"] = {
        "underlying_return_5s": np.array([0.002] * 8, dtype=float),
        "underlying_trade_count": np.array([10.0] * 8, dtype=float),
    }
    _assert_parity("S15", [m], tmp_path)


def test_s16_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s16_config, "get_param_grid", lambda: {
        "short_window": [5], "long_window": [10], "entry_window_start": [1], "entry_window_end": [6],
        "min_short_return": [0.001], "min_long_return_opposite": [0.001], "min_price_distance_from_mid": [0.04],
        "max_underlying_vol": [0.02], "stop_loss": [0.20], "take_profit": [0.80],
    })
    m = _base_market(base_started_at, "s16")
    m["final_outcome"] = "Up"
    m["prices"] = np.array([0.40, 0.42, 0.44, 0.46, 0.47, 0.48, 0.52, 0.56], dtype=float)
    m["feature_series"] = {
        "underlying_return_5s": np.array([0.002] * 8, dtype=float),
        "underlying_return_10s": np.array([-0.002] * 8, dtype=float),
        "underlying_realized_vol_10s": np.array([0.005] * 8, dtype=float),
    }
    _assert_parity("S16", [m], tmp_path)


def test_s17_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s17_config, "get_param_grid", lambda: {
        "entry_window_start": [1], "entry_window_end": [6], "underlying_beta": [20.0], "residual_threshold": [0.02],
        "min_underlying_move_abs": [0.001], "reversal_confirmation_abs": [0.001], "extreme_price_low": [0.25], "extreme_price_high": [0.65],
        "stop_loss": [0.20], "take_profit": [0.80],
    })
    m = _base_market(base_started_at, "s17")
    m["final_outcome"] = "Down"
    m["prices"] = np.array([0.62, 0.66, 0.70, 0.72, 0.68, 0.64, 0.58, 0.54], dtype=float)
    m["feature_series"] = {
        "market_up_delta_from_market_open": np.array([0.05] * 8, dtype=float),
        "underlying_return_from_market_open": np.array([0.001] * 8, dtype=float),
        "market_up_delta_5s": np.array([-0.01] * 8, dtype=float),
    }
    _assert_parity("S17", [m], tmp_path)


def test_s18_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s18_config, "get_param_grid", lambda: {
        "entry_window_start": [1], "entry_window_end": [6], "min_return_30s": [0.001], "min_return_10s": [0.001],
        "min_return_5s": [0.001], "acceleration_ratio": [0.5], "max_underlying_vol": [0.02], "min_trade_count": [5.0],
        "max_price_distance_from_mid": [0.20], "stop_loss": [0.20], "take_profit": [0.80],
    })
    m = _base_market(base_started_at, "s18")
    m["final_outcome"] = "Up"
    m["prices"] = np.array([0.52, 0.54, 0.56, 0.58, 0.60, 0.62, 0.65, 0.68], dtype=float)
    m["feature_series"] = {
        "underlying_return_5s": np.array([0.002] * 8, dtype=float),
        "underlying_return_10s": np.array([0.002] * 8, dtype=float),
        "underlying_return_30s": np.array([0.002] * 8, dtype=float),
        "underlying_realized_vol_30s": np.array([0.005] * 8, dtype=float),
        "underlying_trade_count": np.array([10.0] * 8, dtype=float),
        "market_up_delta_5s": np.array([0.001] * 8, dtype=float),
    }
    _assert_parity("S18", [m], tmp_path)


def test_s19_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(s19_config, "get_param_grid", lambda: {
        "entry_window_start": [1], "entry_window_end": [6], "feature_window": [5], "min_underlying_return": [0.001],
        "min_market_delta": [0.001], "max_market_delta": [0.05], "min_trade_count": [5.0], "min_volume": [0.0],
        "buy_imbalance_threshold": [0.10], "max_price_distance_from_mid": [0.20], "stop_loss": [0.20], "take_profit": [0.80],
    })
    m = _base_market(base_started_at, "s19")
    m["final_outcome"] = "Up"
    m["prices"] = np.array([0.52, 0.54, 0.56, 0.58, 0.60, 0.62, 0.65, 0.68], dtype=float)
    m["feature_series"] = {
        "underlying_return_5s": np.array([0.002] * 8, dtype=float),
        "market_up_delta_5s": np.array([0.003] * 8, dtype=float),
        "underlying_volume": np.array([10.0] * 8, dtype=float),
        "underlying_taker_buy_base_volume": np.array([7.0] * 8, dtype=float),
        "underlying_trade_count": np.array([10.0] * 8, dtype=float),
    }
    _assert_parity("S19", [m], tmp_path)
