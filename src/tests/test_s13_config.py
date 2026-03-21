from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from analysis.backtest_strategies import run_strategy
from shared.strategies.S13.config import get_candidate_config, get_default_config
from shared.strategies.S13.strategy import S13Strategy
from shared.strategies.base import MarketSnapshot


def test_s13_default_matches_candidate():
    cfg = get_default_config()
    candidate = get_candidate_config()

    assert cfg == candidate
    assert cfg.allowed_durations_minutes == [5]
    assert cfg.feature_window == 5
    assert cfg.entry_window_start == 20
    assert cfg.entry_window_end == 240
    assert cfg.min_underlying_return == 0.001
    assert cfg.min_market_confirmation == 0.0
    assert cfg.max_market_delta == 0.05
    assert cfg.max_price_distance_from_mid == 0.20
    assert cfg.max_underlying_vol == 0.006
    assert cfg.live_stop_loss_price == 0.25
    assert cfg.live_take_profit_price == 0.80


def test_s13_signal_includes_live_exit_prices():
    cfg = get_default_config()
    prices = np.full(40, np.nan, dtype=float)
    prices[20] = 0.55

    snapshot = MarketSnapshot(
        market_id="s13_test_market",
        market_type="eth_5m",
        prices=prices,
        total_seconds=300,
        elapsed_seconds=20,
        feature_series={
            "underlying_return_5s": np.full(40, 0.002, dtype=float),
            "market_up_delta_5s": np.full(40, 0.02, dtype=float),
            "underlying_realized_vol_10s": np.full(40, 0.005, dtype=float),
        },
        metadata={
            "asset": "eth",
            "duration_minutes": 5,
            "hour": 20,
            "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        },
    )

    signal = S13Strategy(cfg).evaluate(snapshot)

    assert signal is not None
    assert signal.direction == "Up"
    assert signal.signal_data["stop_loss_price"] == 0.25
    assert signal.signal_data["take_profit_price"] == 0.80


def test_s13_backtest_uses_signal_stop_and_take_profit():
    prices = np.full(31, np.nan, dtype=float)
    prices[20] = 0.55
    prices[21] = 0.57
    prices[22] = 0.81

    market = {
        "market_id": "s13_tp_market",
        "market_type": "eth_5m",
        "asset": "eth",
        "duration_minutes": 5,
        "total_seconds": len(prices),
        "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        "final_outcome": "Up",
        "hour": 20,
        "prices": prices,
        "feature_series": {
            "underlying_return_5s": np.full(len(prices), 0.002, dtype=float),
            "market_up_delta_5s": np.full(len(prices), 0.02, dtype=float),
            "underlying_realized_vol_10s": np.full(len(prices), 0.005, dtype=float),
        },
    }

    trades, metrics = run_strategy(
        "S13",
        S13Strategy(get_default_config()),
        [market],
        slippage=0.0,
        log_summary=False,
    )

    assert len(trades) == 1
    assert trades[0].exit_reason == "tp"
    assert trades[0].second_exited == 22
    assert trades[0].exit_price == 0.81
    assert trades[0].exit_fee_usdc > 0.0
    assert metrics["total_exit_fees"] > 0.0
    assert metrics["stop_loss"] == 0.25
    assert metrics["take_profit"] == 0.80


def test_s13_skips_non_candidate_duration():
    prices = np.full(31, np.nan, dtype=float)
    prices[20] = 0.55

    snapshot = MarketSnapshot(
        market_id="s13_15m_market",
        market_type="eth_15m",
        prices=prices,
        total_seconds=900,
        elapsed_seconds=20,
        feature_series={
            "underlying_return_5s": np.full(len(prices), 0.002, dtype=float),
            "market_up_delta_5s": np.full(len(prices), 0.02, dtype=float),
            "underlying_realized_vol_10s": np.full(len(prices), 0.005, dtype=float),
        },
        metadata={
            "asset": "eth",
            "duration_minutes": 15,
            "hour": 20,
            "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        },
    )

    signal = S13Strategy(get_default_config()).evaluate(snapshot)

    assert signal is None
