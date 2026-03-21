from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from analysis.backtest_strategies import run_strategy
from shared.strategies.S14.config import (
    get_baseline_config,
    get_candidate_config,
    get_default_config,
)
from shared.strategies.S14.strategy import S14Strategy
from shared.strategies.base import MarketSnapshot


def _make_feature_series(length: int) -> dict[str, np.ndarray]:
    return {
        "underlying_return_30s": np.full(length, 0.0005, dtype=float),
        "market_up_delta_30s": np.full(length, -0.06, dtype=float),
        "direction_mismatch_30s": np.full(length, 1.0, dtype=float),
    }


def test_s14_default_matches_research_candidate():
    cfg = get_default_config()
    candidate = get_candidate_config()
    baseline = get_baseline_config()

    assert cfg == candidate
    assert cfg.allowed_durations_minutes == [5]
    assert cfg.feature_window == 30
    assert cfg.entry_window_start == 30
    assert cfg.entry_window_end == 240
    assert cfg.min_market_delta_abs == 0.06
    assert cfg.max_underlying_return_abs == 0.0015
    assert cfg.extreme_price_low == 0.35
    assert cfg.extreme_price_high == 0.65
    assert cfg.require_direction_mismatch is True
    assert cfg.live_stop_loss_price == 0.25
    assert cfg.live_take_profit_price == 0.75

    assert baseline.feature_window == 10
    assert baseline.entry_window_start == 20
    assert baseline.entry_window_end == 210
    assert baseline.min_market_delta_abs == 0.04
    assert baseline.max_underlying_return_abs == 0.0008
    assert baseline.extreme_price_low == 0.30
    assert baseline.extreme_price_high == 0.70
    assert baseline.live_stop_loss_price == 0.30
    assert baseline.live_take_profit_price == 0.70


def test_s14_signal_includes_live_exit_prices():
    prices = np.full(46, np.nan, dtype=float)
    prices[45] = 0.34

    snapshot = MarketSnapshot(
        market_id="s14_test_market",
        market_type="eth_5m",
        prices=prices,
        total_seconds=300,
        elapsed_seconds=45,
        feature_series=_make_feature_series(len(prices)),
        metadata={
            "asset": "eth",
            "duration_minutes": 5,
            "hour": 20,
            "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        },
    )

    signal = S14Strategy(get_default_config()).evaluate(snapshot)

    assert signal is not None
    assert signal.direction == "Up"
    assert signal.signal_data["stop_loss_price"] == 0.25
    assert signal.signal_data["take_profit_price"] == 0.75


def test_s14_skips_non_candidate_duration():
    prices = np.full(46, np.nan, dtype=float)
    prices[30] = 0.34

    snapshot = MarketSnapshot(
        market_id="s14_15m_market",
        market_type="eth_15m",
        prices=prices,
        total_seconds=900,
        elapsed_seconds=30,
        feature_series=_make_feature_series(len(prices)),
        metadata={
            "asset": "eth",
            "duration_minutes": 15,
            "hour": 20,
            "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        },
    )

    signal = S14Strategy(get_default_config()).evaluate(snapshot)

    assert signal is None


def test_s14_backtest_uses_signal_stop_and_take_profit():
    prices = np.full(48, np.nan, dtype=float)
    prices[30] = 0.34
    prices[31] = 0.50
    prices[32] = 0.76

    market = {
        "market_id": "s14_tp_market",
        "market_type": "eth_5m",
        "asset": "eth",
        "duration_minutes": 5,
        "total_seconds": len(prices),
        "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        "final_outcome": "Up",
        "hour": 20,
        "prices": prices,
        "feature_series": _make_feature_series(len(prices)),
    }

    trades, metrics = run_strategy(
        "S14",
        S14Strategy(get_default_config()),
        [market],
        slippage=0.0,
        log_summary=False,
    )

    assert len(trades) == 1
    assert trades[0].exit_reason == "tp"
    assert trades[0].second_exited == 32
    assert trades[0].exit_price == 0.76
    assert trades[0].exit_fee_usdc > 0.0
    assert metrics["total_exit_fees"] > 0.0
    assert metrics["stop_loss"] == 0.25
    assert metrics["take_profit"] == 0.75
