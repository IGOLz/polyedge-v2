from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from analysis.backtest_strategies import run_strategy
from shared.strategies.S15.config import get_candidate_config, get_default_config
from shared.strategies.S15.strategy import S15Strategy
from shared.strategies.base import MarketSnapshot


def _make_feature_series(length: int) -> dict[str, np.ndarray]:
    return {
        "underlying_return_5s": np.full(length, 0.001, dtype=float),
        "underlying_trade_count": np.full(length, 80.0, dtype=float),
    }


def test_s15_default_matches_research_candidate():
    cfg = get_default_config()
    candidate = get_candidate_config()

    assert cfg == candidate
    assert cfg.allowed_assets == ["btc", "eth", "sol", "xrp"]
    assert cfg.allowed_durations_minutes == [5]
    assert cfg.setup_window_end == 30
    assert cfg.breakout_scan_start == 25
    assert cfg.breakout_scan_end == 240
    assert cfg.breakout_buffer == 0.01
    assert cfg.confirmation_points == 1
    assert cfg.feature_window == 5
    assert cfg.min_underlying_return == 0.0005
    assert cfg.min_trade_count == 40.0
    assert cfg.live_stop_loss_price == 0.35
    assert cfg.live_take_profit_price == 0.75


def test_s15_signal_includes_live_exit_prices():
    prices = np.full(36, 0.40, dtype=float)
    prices[31:36] = 0.42

    snapshot = MarketSnapshot(
        market_id="s15_test_market",
        market_type="eth_5m",
        prices=prices,
        total_seconds=300,
        elapsed_seconds=35,
        feature_series=_make_feature_series(len(prices)),
        metadata={
            "asset": "eth",
            "duration_minutes": 5,
            "hour": 20,
            "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        },
    )

    signal = S15Strategy(get_default_config()).evaluate(snapshot)

    assert signal is not None
    assert signal.direction == "Up"
    assert signal.signal_data["stop_loss_price"] == 0.35
    assert signal.signal_data["take_profit_price"] == 0.75


def test_s15_skips_non_candidate_duration():
    prices = np.full(36, 0.40, dtype=float)
    prices[31:36] = 0.42

    snapshot = MarketSnapshot(
        market_id="s15_15m_market",
        market_type="eth_15m",
        prices=prices,
        total_seconds=900,
        elapsed_seconds=35,
        feature_series=_make_feature_series(len(prices)),
        metadata={
            "asset": "eth",
            "duration_minutes": 15,
            "hour": 20,
            "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        },
    )

    signal = S15Strategy(get_default_config()).evaluate(snapshot)

    assert signal is None


def test_s15_backtest_uses_signal_stop_and_take_profit():
    prices = np.full(39, 0.40, dtype=float)
    prices[31:36] = 0.42
    prices[36] = 0.50
    prices[37] = 0.76
    prices[38] = 0.78

    market = {
        "market_id": "s15_tp_market",
        "market_type": "eth_5m",
        "asset": "eth",
        "duration_minutes": 5,
        "total_seconds": len(prices),
        "started_at": datetime(2026, 3, 21, 20, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 3, 21, 20, 5, tzinfo=timezone.utc),
        "final_outcome": "Up",
        "hour": 20,
        "prices": prices,
        "feature_series": _make_feature_series(len(prices)),
    }

    trades, metrics = run_strategy(
        "S15",
        S15Strategy(get_default_config()),
        [market],
        slippage=0.0,
        log_summary=False,
    )

    assert len(trades) == 1
    assert trades[0].exit_reason == "tp"
    assert trades[0].second_exited == 37
    assert trades[0].exit_price == 0.76
    assert trades[0].exit_fee_usdc > 0.0
    assert metrics["total_exit_fees"] > 0.0
    assert metrics["stop_loss"] == 0.35
    assert metrics["take_profit"] == 0.75
