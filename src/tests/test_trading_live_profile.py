from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from shared.strategies.base import MarketSnapshot
from trading.live_profile import (
    build_live_s10_config,
    build_live_s5_config,
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


def test_live_profiles_keep_s5_and_add_s10():
    s5 = build_live_s5_config()
    s10 = build_live_s10_config()

    assert s5.strategy_id == "S5"
    assert s5.entry_window_start == 45
    assert s5.entry_window_end == 180
    assert s5.allowed_hours == [18, 19, 20, 21, 22, 23]
    assert s5.allowed_assets == ["eth", "sol"]
    assert s5.allowed_durations_minutes == [5]
    assert s5.live_stop_loss_price == 0.35
    assert s5.live_take_profit_price == 0.70

    assert s10.strategy_id == "S10"
    assert s10.allowed_hours is None
    assert s10.allowed_assets == ["btc", "eth", "sol", "xrp"]
    assert s10.allowed_durations_minutes == [5, 15]
    assert s10.impulse_start == 20
    assert s10.impulse_end == 45
    assert s10.impulse_threshold == 0.05
    assert s10.retrace_window == 30
    assert s10.retrace_max == 0.65
    assert s10.impulse_efficiency_min == 0.75
    assert s10.live_stop_loss_price == 0.40
    assert s10.live_take_profit_price == 0.80


def test_live_market_scope_is_union_of_s5_and_s10():
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


def test_live_strategies_include_both_s5_and_s10():
    strategies = {strategy.config.strategy_id: strategy for strategy in get_live_strategies()}

    assert set(strategies) == {"S5", "S10"}

    s5_signal = strategies["S5"].evaluate(_make_s5_trigger_snapshot(asset="eth", duration_minutes=5, hour=20))
    s10_signal = strategies["S10"].evaluate(_make_s10_trigger_snapshot(asset="btc", duration_minutes=15, hour=13))

    assert s5_signal is not None
    assert s5_signal.strategy_name == "S5_time_phase_midpoint_reclaim"
    assert s10_signal is not None
    assert s10_signal.strategy_name == "S10_pullback_continuation"


def test_live_profile_summary_lists_both_strategies():
    summary = live_profile_summary()

    assert "S5" in summary
    assert "S10" in summary
