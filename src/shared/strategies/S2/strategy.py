"""S2 Strategy: Early Momentum — detect directional velocity in first 30-60 seconds.

Entry logic: Calculate velocity between two time points (30s and 60s).
If velocity >= threshold, enter Down (contrarian to upward momentum).
If velocity <= -threshold, enter Up (contrarian to downward momentum).
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S2.config import S2Config


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


class S2Strategy(BaseStrategy):
    """S2 Strategy: Early Momentum — detect directional velocity in first 30-60 seconds

    Entry logic: Calculate velocity = (price_60s - price_30s) / time_delta.
    If velocity >= threshold, enter Down (contrarian to rising price).
    If velocity <= -threshold, enter Up (contrarian to falling price).
    """

    config: S2Config

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect momentum signal from market snapshot.

        Contract:
        - Pure function: no side effects, no async, no database access.
        - Return a ``Signal`` when entry conditions are met, ``None`` otherwise.
        - Never raise on NaN-heavy, flat, or insufficient data — just return None.
        """
        prices = snapshot.prices
        cfg = self.config

        # Guard: need enough data to reach eval_window_end
        if len(prices) < cfg.eval_window_end:
            return None

        # Get price at eval_window_start (e.g., 30s)
        price_30s = _get_price(prices, cfg.eval_window_start, cfg.tolerance)
        if price_30s is None:
            return None

        # Get price at eval_window_end (e.g., 60s)
        price_60s = _get_price(prices, cfg.eval_window_end, cfg.tolerance)
        if price_60s is None:
            return None

        # Calculate velocity (price change per second)
        time_delta = cfg.eval_window_end - cfg.eval_window_start
        velocity = (price_60s - price_30s) / time_delta

        # Check for strong upward momentum → enter Down (contrarian)
        if velocity >= cfg.momentum_threshold:
            entry_price = max(0.01, min(0.99, 1.0 - price_60s))  # clamp
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=entry_price,
                signal_data={
                    "entry_second": cfg.eval_window_end,
                    "velocity": velocity,
                    "price_30s": price_30s,
                    "price_60s": price_60s,
                },
            )

        # Check for strong downward momentum → enter Up (contrarian)
        if velocity <= -cfg.momentum_threshold:
            entry_price = max(0.01, min(0.99, price_60s))  # clamp
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=entry_price,
                signal_data={
                    "entry_second": cfg.eval_window_end,
                    "velocity": velocity,
                    "price_30s": price_30s,
                    "price_60s": price_60s,
                },
            )

        # No momentum signal detected
        return None
