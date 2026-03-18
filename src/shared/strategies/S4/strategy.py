"""S4 Strategy: Volatility Regime — enter contrarian when high volatility + extreme price.

Entry logic: Calculate rolling volatility at eval_second. Enter contrarian when:
- Volatility (std dev) ≥ vol_threshold (high volatility detected)
- Current price ≤ extreme_price_low → bet Up (fade low extreme)
- Current price ≥ extreme_price_high → bet Down (fade high extreme)

High volatility + extreme price suggests overreaction → fade it.
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S4.config import S4Config


def _get_price(prices: np.ndarray, target_sec: int, tolerance: int = 5) -> float | None:
    """Get price at target second with NaN tolerance.
    
    Args:
        prices: numpy array of prices indexed by elapsed second
        target_sec: target second to retrieve price
        tolerance: seconds to scan ±target_sec if target is NaN
        
    Returns:
        price at target_sec, or nearest valid price within tolerance, or None
    """
    if target_sec < 0 or target_sec >= len(prices):
        return None
    
    # Check target first
    price = prices[target_sec]
    if not np.isnan(price):
        return float(price)
    
    # Scan ±tolerance for nearest valid price
    for offset in range(1, tolerance + 1):
        # Check target_sec + offset
        idx_plus = target_sec + offset
        if idx_plus < len(prices):
            price = prices[idx_plus]
            if not np.isnan(price):
                return float(price)
        
        # Check target_sec - offset
        idx_minus = target_sec - offset
        if idx_minus >= 0:
            price = prices[idx_minus]
            if not np.isnan(price):
                return float(price)
    
    return None


class S4Strategy(BaseStrategy):
    """S4 Strategy: Volatility Regime — enter contrarian only under specific vol conditions

    Entry logic: High volatility + extreme price suggests overreaction. Fade it.
    """

    config: S4Config

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect a trading signal from the market snapshot.

        Contract:
        - Pure function: no side effects, no async, no database access.
        - Return a ``Signal`` when entry conditions are met, ``None`` otherwise.
        - Never raise on NaN-heavy, flat, or insufficient data — just return None.
        """
        prices = snapshot.prices
        cfg = self.config

        # Guard: need to reach eval_second
        if snapshot.elapsed_seconds < cfg.eval_second:
            return None

        # Guard: need enough data for lookback window
        window_start = cfg.eval_second - cfg.lookback_window
        if window_start < 0:
            return None

        # Collect prices from (eval_second - lookback_window) to eval_second
        window_prices = prices[window_start:cfg.eval_second + 1]
        
        # Filter to valid (non-NaN) prices
        valid_prices = window_prices[~np.isnan(window_prices)]
        
        # Need at least 10 valid prices for meaningful volatility calculation
        if len(valid_prices) < 10:
            return None

        # Calculate volatility (standard deviation)
        std_dev = float(np.std(valid_prices))

        # Get current price at eval_second
        current_price = _get_price(prices, cfg.eval_second, tolerance=5)
        if current_price is None:
            return None

        # Check if volatility is high AND price is extreme
        if std_dev >= cfg.vol_threshold:
            # Price too low + high vol → bet Up (fade low extreme)
            if current_price <= cfg.extreme_price_low:
                entry_price = max(0.01, min(0.99, current_price))
                return Signal(
                    direction="Up",
                    strategy_name=cfg.strategy_name,
                    entry_price=entry_price,
                    signal_data={
                        "entry_second": cfg.eval_second,
                        "volatility": std_dev,
                        "current_price": current_price,
                    },
                )
            
            # Price too high + high vol → bet Down (fade high extreme)
            if current_price >= cfg.extreme_price_high:
                entry_price = max(0.01, min(0.99, 1.0 - current_price))
                return Signal(
                    direction="Down",
                    strategy_name=cfg.strategy_name,
                    entry_price=entry_price,
                    signal_data={
                        "entry_second": cfg.eval_second,
                        "volatility": std_dev,
                        "current_price": current_price,
                    },
                )

        # No signal: either volatility not high enough or price not extreme
        return None
