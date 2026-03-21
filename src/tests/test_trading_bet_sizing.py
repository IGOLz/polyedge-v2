from __future__ import annotations

import numpy as np

from shared.strategies.base import MarketSnapshot, Signal
from trading import strategy_adapter
from trading.strategies import calculate_dynamic_bet_size, normalize_strategy_key


def _make_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="btc_5m_test_market",
        market_type="btc_5m",
        prices=np.array([0.50], dtype=float),
        total_seconds=300,
        elapsed_seconds=30,
        metadata={
            "asset": "btc",
            "duration_minutes": 5,
            "hour": 13,
        },
    )


def test_normalize_strategy_key_handles_live_strategy_names():
    assert normalize_strategy_key("S13_underlying_lag_follow") == "S13"
    assert normalize_strategy_key("s10_pullback_continuation") == "S10"
    assert normalize_strategy_key("M3_spike_reversion") == "M3"
    assert normalize_strategy_key("unknown_strategy") == "DEFAULT"


def test_calculate_dynamic_bet_size_uses_strategy_specific_bankroll_slices():
    bankroll = 170.0

    assert calculate_dynamic_bet_size(bankroll, "S13_underlying_lag_follow") == 10.2
    assert calculate_dynamic_bet_size(bankroll, "S9_compression_breakout") == 7.65
    assert calculate_dynamic_bet_size(bankroll, "S14_divergence_fade") == 6.8
    assert calculate_dynamic_bet_size(bankroll, "S5_time_phase_midpoint_reclaim") == 5.95
    assert calculate_dynamic_bet_size(bankroll, "S10_pullback_continuation") == 4.25
    assert calculate_dynamic_bet_size(bankroll, "M3_spike_reversion") == 6.8
    assert calculate_dynamic_bet_size(bankroll, "M4_volatility") == 5.1
    assert calculate_dynamic_bet_size(bankroll, None) == 5.1


def test_calculate_dynamic_bet_size_scales_up_with_balance_growth():
    assert calculate_dynamic_bet_size(340.0, "S13_underlying_lag_follow") == 20.4
    assert calculate_dynamic_bet_size(340.0, "S10_pullback_continuation") == 8.5


def test_adapter_populates_locked_bet_size_from_signal_strategy_name():
    snapshot = _make_snapshot()
    s13_signal = Signal(direction="Up", strategy_name="S13_underlying_lag_follow", entry_price=0.50)
    s10_signal = Signal(direction="Up", strategy_name="S10_pullback_continuation", entry_price=0.50)

    populated_s13 = strategy_adapter._populate_execution_fields(
        s13_signal,
        market=None,
        snapshot=snapshot,
        balance=170.0,
    )
    populated_s10 = strategy_adapter._populate_execution_fields(
        s10_signal,
        market=None,
        snapshot=snapshot,
        balance=170.0,
    )

    assert populated_s13 is not None
    assert populated_s10 is not None
    assert populated_s13.locked_bet_size == 10.2
    assert populated_s10.locked_bet_size == 4.25
    assert populated_s13.locked_bet_size > populated_s10.locked_bet_size
    assert populated_s13.locked_shares == 20
    assert populated_s10.locked_shares == 8
