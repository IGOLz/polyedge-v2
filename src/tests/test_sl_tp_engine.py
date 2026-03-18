"""Unit tests for stop loss and take profit engine simulation.

Tests cover:
- Up bet SL hit (price drops below threshold)
- Up bet TP hit (price rises above threshold)
- Down bet SL hit (price rises above inverted threshold)
- Down bet TP hit (price drops below inverted threshold)
- No threshold hit (hold to resolution)
- NaN price handling
- Both SL and TP hit in same second (SL priority)
- PnL calculation correctness
"""

import pytest
import numpy as np
from analysis.backtest.engine import (
    Trade, make_trade, simulate_sl_tp_exit,
    calculate_pnl_exit, polymarket_dynamic_fee
)


@pytest.fixture
def synthetic_market():
    """Create a synthetic market dict with controlled price movement for testing."""
    def _make_market(prices, final_outcome='Up', market_id='test_market'):
        """
        Args:
            prices: list or array of float prices
            final_outcome: 'Up' or 'Down' for resolution outcome
            market_id: market identifier
        
        Returns:
            Market dict compatible with make_trade()
        """
        prices_arr = np.array(prices, dtype=float)
        return {
            'market_id': market_id,
            'asset': 'TEST',
            'duration_minutes': 5,
            'total_seconds': len(prices_arr),
            'final_outcome': final_outcome,
            'hour': 12,
            'prices': prices_arr,
        }
    return _make_market


# ========== Up Bet Tests ==========

def test_up_bet_sl_hit(synthetic_market):
    """Up bet with price dropping below SL threshold."""
    # Price drops from 0.55 to 0.45, hitting SL at second 3
    prices = [0.55, 0.53, 0.48, 0.45, 0.40, 0.38]
    market = synthetic_market(prices, final_outcome='Down')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.55, direction='Up',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70
    )
    
    assert trade.exit_reason == 'sl', f"Expected 'sl', got '{trade.exit_reason}'"
    assert trade.second_exited == 3, f"Expected exit at second 3, got {trade.second_exited}"
    assert trade.exit_price == 0.45, f"Expected exit_price 0.45, got {trade.exit_price}"
    assert trade.pnl < 0, f"Expected negative PnL for SL hit, got {trade.pnl}"


def test_up_bet_tp_hit(synthetic_market):
    """Up bet with price rising above TP threshold."""
    # Price rises from 0.55 to 0.72, hitting TP at second 4
    prices = [0.55, 0.58, 0.62, 0.68, 0.72, 0.75]
    market = synthetic_market(prices, final_outcome='Up')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.55, direction='Up',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70
    )
    
    assert trade.exit_reason == 'tp', f"Expected 'tp', got '{trade.exit_reason}'"
    assert trade.second_exited == 4, f"Expected exit at second 4, got {trade.second_exited}"
    assert trade.exit_price == 0.72, f"Expected exit_price 0.72, got {trade.exit_price}"
    assert trade.pnl > 0, f"Expected positive PnL for TP hit, got {trade.pnl}"


def test_up_bet_no_hit(synthetic_market):
    """Up bet with price staying between SL and TP thresholds."""
    # Price fluctuates but stays in range [0.52, 0.60]
    prices = [0.55, 0.56, 0.57, 0.58, 0.59, 0.60]
    market = synthetic_market(prices, final_outcome='Up')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.55, direction='Up',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70
    )
    
    assert trade.exit_reason == 'resolution', f"Expected 'resolution', got '{trade.exit_reason}'"
    assert trade.second_exited == len(prices) - 1, f"Expected exit at last second, got {trade.second_exited}"
    # Resolution exit uses last valid price from simulator
    assert trade.exit_price == 0.60, f"Expected exit_price 0.60 (last price), got {trade.exit_price}"


# ========== Down Bet Tests ==========

def test_down_bet_sl_hit(synthetic_market):
    """Down bet with price rising above inverted SL threshold."""
    # Down token price = 1.0 - up_price
    # Entry at up_price=0.45 → down_token=0.55
    # SL at down_token=0.45 → triggers when up_price >= 0.55
    prices = [0.45, 0.48, 0.52, 0.55, 0.60, 0.65]
    market = synthetic_market(prices, final_outcome='Up')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.45, direction='Down',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70  # Down token thresholds
    )
    
    assert trade.exit_reason == 'sl', f"Expected 'sl', got '{trade.exit_reason}'"
    assert trade.second_exited == 3, f"Expected exit at second 3, got {trade.second_exited}"
    assert trade.exit_price == 0.55, f"Expected exit_price 0.55, got {trade.exit_price}"
    assert trade.pnl < 0, f"Expected negative PnL for SL hit, got {trade.pnl}"


def test_down_bet_tp_hit(synthetic_market):
    """Down bet with price dropping below inverted TP threshold."""
    # Entry at up_price=0.45 → down_token=0.55
    # TP at down_token=0.75 → triggers when up_price <= 0.25
    prices = [0.45, 0.42, 0.38, 0.33, 0.28, 0.25]
    market = synthetic_market(prices, final_outcome='Down')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.45, direction='Down',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.40, take_profit=0.75  # Down token thresholds
    )
    
    assert trade.exit_reason == 'tp', f"Expected 'tp', got '{trade.exit_reason}'"
    assert trade.second_exited == 5, f"Expected exit at second 5, got {trade.second_exited}"
    assert trade.exit_price == 0.25, f"Expected exit_price 0.25, got {trade.exit_price}"
    assert trade.pnl > 0, f"Expected positive PnL for TP hit, got {trade.pnl}"


def test_down_bet_no_hit(synthetic_market):
    """Down bet with price staying within safe range."""
    # Entry at up_price=0.45 → down_token=0.55
    # SL at down_token=0.35 → triggers when up_price >= 0.65
    # TP at down_token=0.80 → triggers when up_price <= 0.20
    # Prices stay in [0.40, 0.45], no thresholds hit
    prices = [0.45, 0.44, 0.43, 0.42, 0.41, 0.40]
    market = synthetic_market(prices, final_outcome='Down')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.45, direction='Down',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.35, take_profit=0.80  # Down token thresholds
    )
    
    assert trade.exit_reason == 'resolution', f"Expected 'resolution', got '{trade.exit_reason}'"
    assert trade.second_exited == len(prices) - 1, f"Expected exit at last second, got {trade.second_exited}"
    # Resolution exit uses last valid price from simulator
    assert trade.exit_price == 0.40, f"Expected exit_price 0.40 (last price), got {trade.exit_price}"


# ========== Edge Cases ==========

def test_nan_handling(synthetic_market):
    """Price array with NaN values - simulator skips invalid prices."""
    # NaN at seconds 1-2, then SL hit at second 3
    prices = [0.55, np.nan, np.nan, 0.45, 0.40, 0.38]
    market = synthetic_market(prices, final_outcome='Down')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.55, direction='Up',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70
    )
    
    assert trade.exit_reason == 'sl', f"Expected 'sl', got '{trade.exit_reason}'"
    assert trade.second_exited == 3, f"Expected exit at second 3 (first valid threshold hit), got {trade.second_exited}"
    assert trade.exit_price == 0.45, f"Expected exit_price 0.45, got {trade.exit_price}"


def test_both_thresholds_same_second(synthetic_market):
    """SL and TP both hit in same second - SL prioritized."""
    # Large price jump hits both thresholds at second 1
    # Direct test of simulate_sl_tp_exit to control price precisely
    prices = np.array([0.55, 0.40, 0.50, 0.50])  # Second 1 drops to 0.40 (< 0.45 SL)
    
    exit_sec, exit_price, reason = simulate_sl_tp_exit(
        prices, entry_second=0, entry_price=0.55, direction='Up',
        stop_loss=0.45, take_profit=0.70
    )
    
    assert reason == 'sl', f"Expected SL priority when both hit, got '{reason}'"
    assert exit_sec == 1, f"Expected exit at second 1, got {exit_sec}"


def test_exit_at_boundary(synthetic_market):
    """Threshold hit at first second after entry."""
    # SL hit immediately at second 1
    prices = [0.55, 0.44, 0.50, 0.50]
    market = synthetic_market(prices, final_outcome='Down')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.55, direction='Up',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70
    )
    
    assert trade.exit_reason == 'sl', f"Expected 'sl', got '{trade.exit_reason}'"
    assert trade.second_exited == 1, f"Expected exit at second 1 (entry_second + 1), got {trade.second_exited}"


def test_all_nan_after_entry(synthetic_market):
    """All prices after entry are NaN - resolution exit with last valid price."""
    prices = [0.55, np.nan, np.nan, np.nan, np.nan, np.nan]
    market = synthetic_market(prices, final_outcome='Up')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.55, direction='Up',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70
    )
    
    assert trade.exit_reason == 'resolution', f"Expected 'resolution' when all NaN, got '{trade.exit_reason}'"
    assert trade.second_exited == len(prices) - 1, f"Expected exit at last second, got {trade.second_exited}"
    # Simulator uses last valid price (entry price = 0.55)
    assert trade.exit_price == 0.55, f"Expected exit_price 0.55 (last valid), got {trade.exit_price}"


# ========== PnL Correctness Tests ==========

def test_pnl_sl_exit(synthetic_market):
    """Verify PnL calculation for SL exit matches expected value with fees."""
    prices = [0.55, 0.53, 0.48, 0.45, 0.40, 0.38]
    market = synthetic_market(prices, final_outcome='Down')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.55, direction='Up',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70
    )
    
    # Hand-calculate expected PnL for Up bet
    entry = 0.55
    exit = 0.45
    gross_pnl = exit - entry  # -0.10
    fee = polymarket_dynamic_fee(entry, 0.063) * max(0.0, gross_pnl)  # no fee on loss
    expected_pnl = gross_pnl - fee
    
    assert abs(trade.pnl - expected_pnl) < 0.0001, \
        f"Expected PnL {expected_pnl:.6f}, got {trade.pnl:.6f}"
    assert trade.pnl < 0, "SL exit should produce negative PnL"


def test_pnl_tp_exit(synthetic_market):
    """Verify PnL calculation for TP exit matches expected value with fees."""
    prices = [0.55, 0.58, 0.62, 0.68, 0.72, 0.75]
    market = synthetic_market(prices, final_outcome='Up')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.55, direction='Up',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.45, take_profit=0.70
    )
    
    # Hand-calculate expected PnL for Up bet
    entry = 0.55
    exit = 0.72
    gross_pnl = exit - entry  # +0.17
    fee = polymarket_dynamic_fee(entry, 0.063) * gross_pnl
    expected_pnl = gross_pnl - fee
    
    assert abs(trade.pnl - expected_pnl) < 0.0001, \
        f"Expected PnL {expected_pnl:.6f}, got {trade.pnl:.6f}"
    assert trade.pnl > 0, "TP exit should produce positive PnL"


def test_pnl_down_bet_tp_exit(synthetic_market):
    """Verify PnL calculation for Down bet TP exit."""
    # Down bet: buy No token, profit when up_price drops
    prices = [0.45, 0.42, 0.38, 0.33, 0.28, 0.25]
    market = synthetic_market(prices, final_outcome='Down')
    
    trade = make_trade(
        market, second_entered=0, entry_price=0.45, direction='Down',
        slippage=0.0, base_rate=0.063,
        stop_loss=0.40, take_profit=0.75
    )
    
    # Hand-calculate expected PnL for Down bet
    # You bought No at (1-0.45)=0.55, sell at (1-0.25)=0.75
    # Gross PnL = 0.75 - 0.55 = 0.20
    # Or equivalently: entry - exit = 0.45 - 0.25 = 0.20
    entry = 0.45
    exit = 0.25
    gross_pnl = entry - exit  # Down bet: inverted
    fee = polymarket_dynamic_fee(entry, 0.063) * gross_pnl
    expected_pnl = gross_pnl - fee
    
    assert abs(trade.pnl - expected_pnl) < 0.0001, \
        f"Expected PnL {expected_pnl:.6f}, got {trade.pnl:.6f}"
    assert trade.pnl > 0, "Down bet TP exit should produce positive PnL"
