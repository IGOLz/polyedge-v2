from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from analysis.backtest_strategies import run_strategy
from shared.strategies.S10.config import (
    get_baseline_config,
    get_candidate_config,
    get_default_config,
)
from shared.strategies.S10.strategy import S10Strategy
from shared.strategies.base import MarketSnapshot


def test_s10_default_matches_research_candidate():
    cfg = get_default_config()
    candidate = get_candidate_config()
    baseline = get_baseline_config()

    assert cfg == candidate
    assert cfg.impulse_start == 20
    assert cfg.impulse_end == 45
    assert cfg.impulse_threshold == 0.05
    assert cfg.retrace_window == 30
    assert cfg.retrace_max == 0.65
    assert cfg.reacceleration_threshold == 0.01
    assert cfg.impulse_efficiency_min == 0.75
    assert cfg.live_stop_loss_price == 0.40
    assert cfg.live_take_profit_price == 0.80

    assert baseline.impulse_start == 20
    assert baseline.impulse_end == 60
    assert baseline.impulse_threshold == 0.08
    assert baseline.retrace_window == 30
    assert baseline.retrace_max == 0.45
    assert baseline.reacceleration_threshold == 0.02
    assert baseline.impulse_efficiency_min == 0.65
    assert baseline.live_stop_loss_price == 0.25
    assert baseline.live_take_profit_price == 0.80


def test_s10_signal_includes_live_exit_prices():
    prices = np.full(51, np.nan, dtype=float)
    prices[10:46] = np.linspace(0.30, 0.45, 36)
    prices[46:51] = [0.42, 0.40, 0.41, 0.42, 0.43]

    snapshot = MarketSnapshot(
        market_id="s10_test_market",
        market_type="eth_5m",
        prices=prices,
        total_seconds=300,
        elapsed_seconds=50,
        metadata={
            "asset": "eth",
            "duration_minutes": 5,
            "hour": 20,
            "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        },
    )

    signal = S10Strategy(get_default_config()).evaluate(snapshot)

    assert signal is not None
    assert signal.direction == "Up"
    assert signal.signal_data["stop_loss_price"] == 0.40
    assert signal.signal_data["take_profit_price"] == 0.80


def test_s10_backtest_uses_signal_stop_and_take_profit():
    prices = np.full(53, np.nan, dtype=float)
    prices[10:46] = np.linspace(0.30, 0.45, 36)
    prices[46:51] = [0.42, 0.40, 0.41, 0.42, 0.43]
    prices[51] = 0.82
    prices[52] = 0.84

    market = {
        "market_id": "s10_tp_market",
        "market_type": "eth_5m",
        "asset": "eth",
        "duration_minutes": 5,
        "total_seconds": len(prices),
        "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        "final_outcome": "Up",
        "hour": 20,
        "prices": prices,
        "feature_series": {},
    }

    trades, metrics = run_strategy(
        "S10",
        S10Strategy(get_default_config()),
        [market],
        slippage=0.0,
        log_summary=False,
    )

    assert len(trades) == 1
    assert trades[0].exit_reason == "tp"
    assert trades[0].second_exited == 51
    assert trades[0].exit_price == 0.82
    assert trades[0].exit_fee_usdc > 0.0
    assert metrics["total_exit_fees"] > 0.0
    assert metrics["stop_loss"] == 0.40
    assert metrics["take_profit"] == 0.80
