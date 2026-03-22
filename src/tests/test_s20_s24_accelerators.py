"""Parity tests for accelerated S20-S24 optimizers."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis import optimize
from analysis.accelerators import get_strategy_kernel
from shared.strategies.S20 import config as s20_config
from shared.strategies.S21 import config as s21_config
from shared.strategies.S22 import config as s22_config
from shared.strategies.S23 import config as s23_config
from shared.strategies.S24 import config as s24_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S20").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


def _assert_parity(strategy_id: str, markets: list[dict], tmp_path) -> None:
    generic_df = optimize.optimize_strategy(
        strategy_id,
        markets,
        str(tmp_path / f"{strategy_id.lower()}_generic"),
        workers=1,
        progress_interval=100,
        engine="generic",
        slippage=0.0,
    )
    accelerated_df = optimize.optimize_strategy(
        strategy_id,
        markets,
        str(tmp_path / f"{strategy_id.lower()}_accelerated"),
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


def test_s20_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(
        s20_config,
        "get_param_grid",
        lambda: {
            "checkpoint_tolerance": [2],
            "min_underlying_return_from_open": [0.0015],
            "min_recent_return_5s": [0.0006],
            "underlying_beta": [18.0],
            "min_directional_gap": [0.012],
            "min_market_delta_from_open": [0.01],
            "max_entry_price": [0.78],
            "stop_loss": [0.20],
            "take_profit": [0.80],
        },
    )
    m = _market(base_started_at, "s20")
    m["final_outcome"] = "Up"
    prices = np.full(m["total_seconds"], 0.50, dtype=float)
    prices[39:] = 0.72
    m["prices"] = prices
    ret_open = np.full(m["total_seconds"], np.nan, dtype=float)
    ret_open[39:] = 0.003
    m["feature_series"] = {
        "underlying_return_from_market_open": ret_open,
        "market_up_delta_from_market_open": np.where(np.isfinite(ret_open), 0.03, np.nan),
        "underlying_return_5s": np.where(np.isfinite(ret_open), 0.001, np.nan),
    }
    _assert_parity("S20", [m], tmp_path)


def test_s21_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(
        s21_config,
        "get_param_grid",
        lambda: {
            "max_seconds_to_close": [30],
            "min_seconds_to_close": [3],
            "min_underlying_return_from_open": [0.0015],
            "min_recent_underlying_return_5s": [0.0007],
            "min_recent_market_delta_5s": [0.008],
            "min_market_delta_from_open": [0.02],
            "min_trade_count": [20.0],
            "max_entry_price": [0.82],
            "stop_loss": [0.20],
            "take_profit": [0.80],
        },
    )
    m = _market(base_started_at, "s21")
    m["final_outcome"] = "Up"
    prices = np.full(m["total_seconds"], 0.50, dtype=float)
    prices[69:] = 0.78
    m["prices"] = prices
    active = np.arange(m["total_seconds"]) >= 69
    m["feature_series"] = {
        "underlying_return_from_market_open": np.where(active, 0.003, np.nan),
        "market_up_delta_from_market_open": np.where(active, 0.04, np.nan),
        "underlying_return_5s": np.where(active, 0.001, np.nan),
        "market_up_delta_5s": np.where(active, 0.01, np.nan),
        "underlying_trade_count": np.where(active, 30.0, np.nan),
    }
    _assert_parity("S21", [m], tmp_path)


def test_s22_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(
        s22_config,
        "get_param_grid",
        lambda: {
            "max_seconds_to_close": [3],
            "min_seconds_to_close": [1],
            "min_lead_return_from_open": [0.001],
            "max_lead_return_from_open": [0.02],
            "min_recent_return_5s": [0.0005],
            "min_market_delta_from_open": [0.005],
            "min_trade_count": [10.0],
            "entry_price_floor": [0.60],
            "entry_price_cap": [0.92],
            "stop_loss": [0.20],
            "take_profit": [0.80],
        },
    )
    m = _market(base_started_at, "s22")
    m["final_outcome"] = "Up"
    prices = np.full(m["total_seconds"], 0.50, dtype=float)
    prices[96:] = 0.82
    m["prices"] = prices
    active = np.arange(m["total_seconds"]) >= 96
    m["feature_series"] = {
        "underlying_return_from_market_open": np.where(active, 0.0025, np.nan),
        "market_up_delta_from_market_open": np.where(active, 0.02, np.nan),
        "underlying_return_5s": np.where(active, 0.0008, np.nan),
        "underlying_trade_count": np.where(active, 15.0, np.nan),
    }
    _assert_parity("S22", [m], tmp_path)


def test_s23_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(
        s23_config,
        "get_param_grid",
        lambda: {
            "entry_window_start": [5],
            "entry_window_end": [30],
            "trigger_return_from_open": [0.002],
            "pre_trigger_buffer": [0.0005],
            "min_recent_return_5s": [0.0006],
            "max_market_delta_from_open": [0.04],
            "min_trade_count": [10.0],
            "max_entry_price": [0.80],
            "stop_loss": [0.20],
            "take_profit": [0.80],
        },
    )
    m = _market(base_started_at, "s23", total_seconds=50)
    m["final_outcome"] = "Up"
    prices = np.full(m["total_seconds"], 0.50, dtype=float)
    prices[20:] = 0.74
    m["prices"] = prices
    ret_open = np.full(m["total_seconds"], np.nan, dtype=float)
    ret_open[18] = 0.0010
    ret_open[19] = 0.0017
    ret_open[20:] = 0.0022
    m["feature_series"] = {
        "underlying_return_from_market_open": ret_open,
        "market_up_delta_from_market_open": np.where(np.isfinite(ret_open), 0.015, np.nan),
        "underlying_return_5s": np.where(np.isfinite(ret_open), 0.0008, np.nan),
        "underlying_trade_count": np.where(np.isfinite(ret_open), 12.0, np.nan),
    }
    _assert_parity("S23", [m], tmp_path)


def test_s24_accelerator_matches_generic(tmp_path, monkeypatch, base_started_at):
    monkeypatch.setattr(
        s24_config,
        "get_param_grid",
        lambda: {
            "entry_window_start": [5],
            "entry_window_end": [20],
            "min_underlying_return_from_open": [0.001],
            "min_recent_return_5s": [0.0006],
            "min_market_delta_from_open": [0.0],
            "max_market_delta_from_open": [0.03],
            "min_trade_count": [20.0],
            "min_volume": [0.1],
            "max_entry_price": [0.75],
            "stop_loss": [0.20],
            "take_profit": [0.80],
        },
    )
    m = _market(base_started_at, "s24", total_seconds=60)
    m["final_outcome"] = "Up"
    prices = np.full(m["total_seconds"], 0.50, dtype=float)
    prices[5:] = 0.72
    m["prices"] = prices
    active = np.arange(m["total_seconds"]) >= 5
    m["feature_series"] = {
        "underlying_return_from_market_open": np.where(active, 0.0015, np.nan),
        "market_up_delta_from_market_open": np.where(active, 0.015, np.nan),
        "underlying_return_5s": np.where(active, 0.0008, np.nan),
        "underlying_trade_count": np.where(active, 30.0, np.nan),
        "underlying_volume": np.where(active, 1.0, np.nan),
    }
    _assert_parity("S24", [m], tmp_path)
