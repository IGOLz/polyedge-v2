"""S5 Strategy: Time-Phase Entry — optimal entry timing based on market phase.

Entry logic: Scan entry window for price in target range during allowed hours.
- If price in [price_range_low, price_range_high] during allowed time window
- Direction: if price < 0.50, bet Up (toward middle); if price > 0.50, bet Down
- Hour filter: only enter if current hour in allowed_hours (if specified)

Exploits patterns where certain time phases have better entry success.
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S5.config import S5Config


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


class S5Strategy(BaseStrategy):
    """S5 Strategy: Time-Phase Entry — optimal entry timing based on market phase

    Entry logic: Time-filtered entry when price is near balanced (0.50).
    """

    config: S5Config

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

        # Get current hour from metadata
        current_hour = snapshot.metadata.get('hour')

        # Check hour filter (if specified)
        if cfg.allowed_hours is not None:
            # Handle empty list as no hours allowed
            if len(cfg.allowed_hours) == 0:
                return None
            
            # If hour filter specified and current hour not in allowed list, skip
            if current_hour is not None and current_hour not in cfg.allowed_hours:
                return None

        # Clamp window end to available data
        window_end = min(cfg.entry_window_end, len(prices))

        # Scan entry window for price in target range
        for sec in range(cfg.entry_window_start, window_end):
            price = _get_price(prices, sec, tolerance=5)
            if price is None:
                continue

            # Check if price is in target range
            if cfg.price_range_low <= price <= cfg.price_range_high:
                # Determine direction: bet toward middle (0.50)
                if price < 0.50:
                    direction = "Up"
                    entry_price = max(0.01, min(0.99, price))
                elif price > 0.50:
                    direction = "Down"
                    entry_price = max(0.01, min(0.99, 1.0 - price))
                else:
                    # Price exactly 0.50 — no clear direction, skip
                    continue

                return Signal(
                    direction=direction,
                    strategy_name=cfg.strategy_name,
                    entry_price=entry_price,
                    signal_data={
                        "entry_second": sec,
                        "price": price,
                        "hour": current_hour,
                    },
                )

        # No valid entry found in window
        return None
