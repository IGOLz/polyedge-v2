"""Unit tests for fee-aware stop-loss / take-profit backtest logic."""

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis.backtest.engine import make_trade, polymarket_dynamic_fee, simulate_sl_tp_exit


@pytest.fixture
def synthetic_market():
    """Create a synthetic market dict with controlled price movement for testing."""

    def _make_market(
        prices,
        final_outcome="Up",
        market_id="test_market",
        started_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    ):
        prices_arr = np.array(prices, dtype=float)
        return {
            "market_id": market_id,
            "asset": "BTC",
            "duration_minutes": 5,
            "total_seconds": len(prices_arr),
            "final_outcome": final_outcome,
            "hour": 12,
            "prices": prices_arr,
            "started_at": started_at,
        }

    return _make_market


def test_fee_formula_matches_official_crypto_curve():
    fee = polymarket_dynamic_fee(0.50)
    assert abs(fee - 0.0078) < 0.0001


def test_up_bet_sl_hit(synthetic_market):
    prices = [0.55, 0.53, 0.48, 0.45, 0.40, 0.38]
    market = synthetic_market(prices, final_outcome="Down")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Up",
        stop_loss=0.45,
        take_profit=0.70,
    )

    assert trade.exit_reason == "sl"
    assert trade.second_exited == 3
    assert trade.exit_price == 0.45
    assert trade.pnl < 0


def test_up_bet_tp_hit(synthetic_market):
    prices = [0.55, 0.58, 0.62, 0.68, 0.72, 0.75]
    market = synthetic_market(prices, final_outcome="Up")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Up",
        stop_loss=0.45,
        take_profit=0.70,
    )

    assert trade.exit_reason == "tp"
    assert trade.second_exited == 4
    assert trade.exit_price == 0.72
    assert trade.pnl > 0


def test_up_bet_no_hit_goes_to_resolution(synthetic_market):
    prices = [0.55, 0.56, 0.57, 0.58, 0.59, 0.60]
    market = synthetic_market(prices, final_outcome="Up")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Up",
        stop_loss=0.45,
        take_profit=0.70,
    )

    assert trade.exit_reason == "resolution"
    assert trade.second_exited == len(prices) - 1
    assert trade.exit_price == 1.0


def test_down_bet_sl_hit(synthetic_market):
    prices = [0.45, 0.48, 0.52, 0.55, 0.60, 0.65]
    market = synthetic_market(prices, final_outcome="Up")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Down",
        stop_loss=0.45,
        take_profit=0.70,
    )

    assert trade.exit_reason == "sl"
    assert trade.second_exited == 3
    assert trade.exit_price == 0.45
    assert trade.pnl < 0


def test_down_bet_tp_hit(synthetic_market):
    prices = [0.45, 0.42, 0.38, 0.33, 0.28, 0.25]
    market = synthetic_market(prices, final_outcome="Down")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Down",
        stop_loss=0.40,
        take_profit=0.75,
    )

    assert trade.exit_reason == "tp"
    assert trade.second_exited == 5
    assert trade.exit_price == 0.75
    assert trade.pnl > 0


def test_down_bet_no_hit_goes_to_resolution(synthetic_market):
    prices = [0.45, 0.44, 0.43, 0.42, 0.41, 0.40]
    market = synthetic_market(prices, final_outcome="Down")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Down",
        stop_loss=0.35,
        take_profit=0.80,
    )

    assert trade.exit_reason == "resolution"
    assert trade.second_exited == len(prices) - 1
    assert trade.exit_price == 1.0


def test_nan_handling(synthetic_market):
    prices = [0.55, np.nan, np.nan, 0.45, 0.40, 0.38]
    market = synthetic_market(prices, final_outcome="Down")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Up",
        stop_loss=0.45,
        take_profit=0.70,
    )

    assert trade.exit_reason == "sl"
    assert trade.second_exited == 3
    assert trade.exit_price == 0.45


def test_simulator_resolution_when_no_threshold_hit():
    prices = np.array([0.55, 0.56, 0.57, 0.58])
    exit_sec, exit_price, reason = simulate_sl_tp_exit(
        prices,
        entry_second=0,
        entry_price=0.55,
        direction="Up",
        stop_loss=0.45,
        take_profit=0.70,
    )

    assert reason == "resolution"
    assert exit_sec == -1
    assert exit_price is None


def test_pnl_tp_exit_matches_manual_fee_aware_calculation(synthetic_market):
    prices = [0.55, 0.58, 0.62, 0.68, 0.72, 0.75]
    market = synthetic_market(prices, final_outcome="Up")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Up",
        stop_loss=0.45,
        take_profit=0.70,
    )

    entry_fee = polymarket_dynamic_fee(0.55)
    net_shares = 1.0 - (entry_fee / 0.55)
    exit_fee = polymarket_dynamic_fee(0.72, shares=net_shares)
    expected_pnl = net_shares * 0.72 - exit_fee - 0.55

    assert abs(trade.pnl - expected_pnl) < 0.0001


def test_down_tp_exit_matches_manual_fee_aware_calculation(synthetic_market):
    prices = [0.45, 0.42, 0.38, 0.33, 0.28, 0.25]
    market = synthetic_market(prices, final_outcome="Down")

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Down",
        stop_loss=0.40,
        take_profit=0.75,
    )

    entry_fee = polymarket_dynamic_fee(0.55)
    net_shares = 1.0 - (entry_fee / 0.55)
    exit_fee = polymarket_dynamic_fee(0.75, shares=net_shares)
    expected_pnl = net_shares * 0.75 - exit_fee - 0.55

    assert abs(trade.pnl - expected_pnl) < 0.0001


def test_pre_activation_market_is_fee_free(synthetic_market):
    market = synthetic_market(
        [0.55, 0.56, 0.57, 0.58],
        final_outcome="Up",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    trade = make_trade(
        market,
        second_entered=0,
        entry_price=0.55,
        direction="Up",
    )

    assert trade.entry_fee_usdc == 0.0
    assert abs(trade.pnl - (1.0 - 0.55)) < 0.0001
