from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from shared.strategies.base import MarketSnapshot
from trading.live_profile import build_live_s5_config, get_live_strategies, market_in_live_scope


def _make_trigger_snapshot(*, asset: str, duration_minutes: int, hour: int) -> MarketSnapshot:
    prices = np.full(51, 0.47, dtype=float)
    prices[45] = 0.49
    prices[46] = 0.50
    prices[47] = 0.51
    prices[48] = 0.52
    prices[49] = 0.53
    prices[50] = 0.54

    return MarketSnapshot(
        market_id=f"{asset}_{duration_minutes}m_market",
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


def test_live_market_scope_filters_to_eth_sol_5m_and_hours():
    started_at = datetime(2026, 3, 19, 20, 0, tzinfo=timezone.utc)

    assert market_in_live_scope("eth_5m", started_at) is True
    assert market_in_live_scope("sol_5m", started_at) is True
    assert market_in_live_scope("btc_5m", started_at) is False
    assert market_in_live_scope("xrp_5m", started_at) is False
    assert market_in_live_scope("eth_15m", started_at) is False
    assert market_in_live_scope("eth_5m", datetime(2026, 3, 19, 13, 0, tzinfo=timezone.utc)) is False


def test_live_strategy_emits_signal_only_for_allowed_scope():
    strategy = get_live_strategies()[0]

    allowed = _make_trigger_snapshot(asset="eth", duration_minutes=5, hour=20)
    blocked_asset = _make_trigger_snapshot(asset="btc", duration_minutes=5, hour=20)
    blocked_duration = _make_trigger_snapshot(asset="eth", duration_minutes=15, hour=20)
    blocked_hour = _make_trigger_snapshot(asset="eth", duration_minutes=5, hour=13)

    assert strategy.evaluate(allowed) is not None
    assert strategy.evaluate(blocked_asset) is None
    assert strategy.evaluate(blocked_duration) is None
    assert strategy.evaluate(blocked_hour) is None
