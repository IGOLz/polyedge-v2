"""S1 Strategy: Calibration Mispricing — exploit systematic bias in 50/50 pricing.

Entry logic: Enter contrarian when price deviates significantly from balanced (0.50).
If price < 0.45, bet Up. If price > 0.55, bet Down. Evaluation window 30-60s.
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S1.config import S1Config


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


class S1Strategy(BaseStrategy):
    """S1 Strategy: Calibration Mispricing — exploit systematic bias in 50/50 pricing

    Entry logic: Scan entry_window for price deviation from 0.50.
    If price < price_low_threshold and deviation >= min_deviation, bet Up (contrarian).
    If price > price_high_threshold and deviation >= min_deviation, bet Down (contrarian).
    """

    config: S1Config

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect calibration mispricing signal from market snapshot.

        Contract:
        - Pure function: no side effects, no async, no database access.
        - Return a ``Signal`` when entry conditions are met, ``None`` otherwise.
        - Never raise on NaN-heavy, flat, or insufficient data — just return None.
        """
        prices = snapshot.prices
        cfg = self.config

        # Guard: need enough data to reach entry window
        if len(prices) < cfg.entry_window_start:
            return None

        # Scan prices in entry window for deviation from 0.50
        window_end = min(cfg.entry_window_end, len(prices))
        
        for sec in range(cfg.entry_window_start, window_end):
            price = _get_price(prices, sec, tolerance=5)
            if price is None:
                continue
            
            # Check for low price → bet Up (contrarian)
            if price < cfg.price_low_threshold:
                deviation = 0.50 - price
                if deviation >= cfg.min_deviation:
                    entry_price = max(0.01, min(0.99, price))  # clamp
                    return Signal(
                        direction="Up",
                        strategy_name=cfg.strategy_name,
                        entry_price=entry_price,
                        signal_data={
                            "entry_second": sec,
                            "deviation": deviation,
                            "price": price,
                        },
                    )
            
            # Check for high price → bet Down (contrarian)
            if price > cfg.price_high_threshold:
                deviation = price - 0.50
                if deviation >= cfg.min_deviation:
                    entry_price = max(0.01, min(0.99, 1.0 - price))  # clamp
                    return Signal(
                        direction="Down",
                        strategy_name=cfg.strategy_name,
                        entry_price=entry_price,
                        signal_data={
                            "entry_second": sec,
                            "deviation": deviation,
                            "price": price,
                        },
                    )
        
        # No signal detected in entry window
        return None
