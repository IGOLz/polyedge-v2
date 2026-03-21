from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from shared.strategies.base import MarketSnapshot
from trading.live_profile import (
    LIVE_STRATEGY_ENABLED,
    build_live_s5_config,
    build_live_s9_config,
    build_live_s10_config,
    get_live_strategies,
    live_profile_summary,
    market_in_live_scope,
)


def _make_s5_trigger_snapshot(*, asset: str, duration_minutes: int, hour: int) -> MarketSnapshot:
    prices = np.full(51, 0.47, dtype=float)
    prices[45] = 0.49
    prices[46] = 0.50
    prices[47] = 0.51
    prices[48] = 0.52
    prices[49] = 0.53
    prices[50] = 0.54

    return MarketSnapshot(
        market_id=f"{asset}_{duration_minutes}m_s5_market",
        market_type=f"{asset}_{duration_minutes}m",
        prices=prices,
        total_seconds=300,
        elapsed_seconds=50,
        metadata={
            "asset": asset,
            "duration_minutes": duration_minutes,
            "hour": hour,
            "started_at": datetime(2026, 3, 19, hour, 0, tzinfo=timezone.utc),
        },
    )


def _make_s10_trigger_snapshot(*, asset: str, duration_minutes: int, hour: int) -> MarketSnapshot:
    prices = np.full(51, np.nan, dtype=float)
    prices[20:46] = np.linspace(0.30, 0.45, 26)
    prices[46:51] = [0.42, 0.40, 0.41, 0.42, 0.43]

    return MarketSnapshot(
        market_id=f"{asset}_{duration_minutes}m_s10_market",
        market_type=f"{asset}_{duration_minutes}m",
        prices=prices,
        total_seconds=duration_minutes * 60,
        elapsed_seconds=50,
        metadata={
            "asset": asset,
            "duration_minutes": duration_minutes,
            "hour": hour,
            "started_at": datetime(2026, 3, 19, hour, 0, tzinfo=timezone.utc),
        },
    )


def _make_s9_trigger_snapshot(*, asset: str, duration_minutes: int, hour: int) -> MarketSnapshot:
    prices = np.array([
        0.50, 0.501, 0.499, 0.500, 0.501,
        0.500, 0.499, 0.500, 0.501, 0.500,
        0.499, 0.500, 0.500, 0.501, 0.500,
        0.499, 0.500, 0.501, 0.500, 0.500,
        0.505, 0.510, 0.515, 0.520, 0.525,
        0.530, 0.535, 0.540, 0.545, 0.550,
        0.555,
    ], dtype=float)

    return MarketSnapshot(
        market_id=f"{asset}_{duration_minutes}m_market",
        market_type=f"{asset}_{duration_minutes}m",
        prices=prices,
        total_seconds=300,
        elapsed_seconds=30,
        metadata={
            "asset": asset,
            "duration_minutes": duration_minutes,
            "hour": hour,
            "started_at": datetime(2026, 3, 19, hour, 0, tzinfo=timezone.utc),
        },
    )


def test_live_s5_profile_matches_validated_candidate():
    cfg = build_live_s5_config()

    assert cfg.strategy_id == "S5"
    assert cfg.entry_window_start == 45
    assert cfg.entry_window_end == 180
    assert cfg.allowed_hours == [18, 19, 20, 21, 22, 23]
    assert cfg.allowed_assets == ["eth", "sol"]
    assert cfg.allowed_durations_minutes == [5]
    assert cfg.price_range_low == 0.45
    assert cfg.price_range_high == 0.60
    assert cfg.approach_lookback == 12
    assert cfg.cross_buffer == 0.02
    assert cfg.confirmation_lookback == 5
    assert cfg.confirmation_min_move == 0.01
    assert cfg.min_cross_move == 0.04
    assert cfg.live_stop_loss_price == 0.35
    assert cfg.live_take_profit_price == 0.70


def test_live_s9_profile_matches_validated_candidate():
    cfg = build_live_s9_config()

    assert cfg.strategy_id == "S9"
    assert cfg.allowed_assets == ["btc", "eth", "sol", "xrp"]
    assert cfg.allowed_durations_minutes == [5]
    assert cfg.compression_window == 20
    assert cfg.compression_max_std == 0.008
    assert cfg.compression_max_range == 0.03
    assert cfg.trigger_scan_start == 30
    assert cfg.trigger_scan_end == 180
    assert cfg.breakout_distance == 0.03
    assert cfg.momentum_lookback == 15
    assert cfg.efficiency_min == 0.55
    assert cfg.live_stop_loss_price == 0.40
    assert cfg.live_take_profit_price == 0.70


def test_live_s10_profile_matches_validated_candidate():
    cfg = build_live_s10_config()

    assert cfg.strategy_id == "S10"
    assert cfg.allowed_hours is None
    assert cfg.allowed_assets == ["btc", "eth", "sol", "xrp"]
    assert cfg.allowed_durations_minutes == [5, 15]
    assert cfg.impulse_start == 20
    assert cfg.impulse_end == 45
    assert cfg.impulse_threshold == 0.05
    assert cfg.retrace_window == 30
    assert cfg.retrace_min == 0.10
    assert cfg.retrace_max == 0.65
    assert cfg.reacceleration_threshold == 0.01
    assert cfg.impulse_efficiency_min == 0.75
    assert cfg.live_stop_loss_price == 0.40
    assert cfg.live_take_profit_price == 0.80


def test_live_market_scope_is_union_of_s5_s9_and_s10():
    evening = datetime(2026, 3, 19, 20, 0, tzinfo=timezone.utc)
    afternoon = datetime(2026, 3, 19, 13, 0, tzinfo=timezone.utc)

    assert market_in_live_scope("eth_5m", evening) is True
    assert market_in_live_scope("sol_5m", evening) is True
    assert market_in_live_scope("btc_5m", evening) is True
    assert market_in_live_scope("xrp_15m", afternoon) is True
    assert market_in_live_scope("eth_15m", afternoon) is True
    assert market_in_live_scope("doge_5m", evening) is False
    assert market_in_live_scope("eth_30m", evening) is False
    assert market_in_live_scope("btc_30m", afternoon) is False


def test_live_profile_enables_all_three_strategies_by_default():
    strategies = get_live_strategies()
    summary = live_profile_summary()

    assert [strategy.config.strategy_id for strategy in strategies] == ["S5", "S9", "S10"]
    assert "S5" in summary
    assert "S9" in summary
    assert "S10" in summary


def test_live_profile_can_toggle_strategy_subset(monkeypatch):
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S5", True)
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S9", True)
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S10", False)
    get_live_strategies.cache_clear()

    try:
        strategies = get_live_strategies()
        summary = live_profile_summary()

        assert [strategy.config.strategy_id for strategy in strategies] == ["S5", "S9"]
        assert "S5" in summary
        assert "S9" in summary
        assert "S10" not in summary
        assert market_in_live_scope("btc_5m", datetime(2026, 3, 19, 20, 0, tzinfo=timezone.utc)) is True
        assert market_in_live_scope("eth_15m", datetime(2026, 3, 19, 20, 0, tzinfo=timezone.utc)) is False
    finally:
        monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S10", True)
        get_live_strategies.cache_clear()


def test_live_s5_strategy_emits_signal_only_for_allowed_scope(monkeypatch):
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S5", True)
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S9", False)
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S10", False)
    get_live_strategies.cache_clear()

    try:
        strategy = get_live_strategies()[0]
        allowed = _make_s5_trigger_snapshot(asset="eth", duration_minutes=5, hour=20)
        blocked_asset = _make_s5_trigger_snapshot(asset="btc", duration_minutes=5, hour=20)
        blocked_duration = _make_s5_trigger_snapshot(asset="eth", duration_minutes=15, hour=20)
        blocked_hour = _make_s5_trigger_snapshot(asset="eth", duration_minutes=5, hour=13)

        assert strategy.evaluate(allowed) is not None
        assert strategy.evaluate(blocked_asset) is None
        assert strategy.evaluate(blocked_duration) is None
        assert strategy.evaluate(blocked_hour) is None
    finally:
        monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S9", True)
        monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S10", True)
        get_live_strategies.cache_clear()


def test_live_s9_strategy_emits_signal_only_for_allowed_scope(monkeypatch):
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S5", False)
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S9", True)
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S10", False)
    get_live_strategies.cache_clear()

    try:
        strategy = get_live_strategies()[0]
        allowed = _make_s9_trigger_snapshot(asset="btc", duration_minutes=5, hour=20)
        blocked_asset = _make_s9_trigger_snapshot(asset="doge", duration_minutes=5, hour=20)
        blocked_duration = _make_s9_trigger_snapshot(asset="btc", duration_minutes=15, hour=20)

        assert strategy.evaluate(allowed) is not None
        assert strategy.evaluate(blocked_asset) is None
        assert strategy.evaluate(blocked_duration) is None
    finally:
        monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S5", True)
        monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S10", True)
        get_live_strategies.cache_clear()


def test_live_s10_strategy_emits_signal_when_enabled(monkeypatch):
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S5", False)
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S9", False)
    monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S10", True)
    get_live_strategies.cache_clear()

    try:
        strategy = get_live_strategies()[0]
        signal = strategy.evaluate(_make_s10_trigger_snapshot(asset="btc", duration_minutes=15, hour=13))

        assert strategy.config.strategy_id == "S10"
        assert signal is not None
        assert signal.strategy_name == "S10_pullback_continuation"
    finally:
        monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S5", True)
        monkeypatch.setitem(LIVE_STRATEGY_ENABLED, "S9", True)
        get_live_strategies.cache_clear()
