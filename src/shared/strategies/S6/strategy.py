"""S6 Strategy: Streak/Sequence — detect consecutive same-direction moves

This strategy detects consecutive same-direction price moves within a single
market and enters contrarian when streak length reaches threshold.

Note: This is a simplified intra-market version that detects consecutive
same-direction price moves within one market. The original streak strategy
tracked consecutive same-outcome markets across sequential markets, which
requires cross-market state and cannot be implemented within the pure
function contract. True cross-market streak detection would require the
backtest runner to track streaks and inject state via snapshot.metadata.
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S6.config import S6Config


def _get_price(prices: np.ndarray, target_sec: int, tolerance: int = 5) -> float | None:
    """Get price at target second with NaN tolerance.

    If target_sec is out of bounds or NaN, scan within ±tolerance range
    for first valid price.

    Args:
        prices: Price array from MarketSnapshot
        target_sec: Target second to look up
        tolerance: Window to scan if target is NaN or out of bounds

    Returns:
        Price as float, or None if no valid price found in window
    """
    if target_sec < 0 or target_sec >= len(prices):
        return None

    # Try exact match first
    val = prices[target_sec]
    if not np.isnan(val):
        return float(val)

    # Scan within tolerance
    for offset in range(1, tolerance + 1):
        # Try forward
        if target_sec + offset < len(prices):
            val = prices[target_sec + offset]
            if not np.isnan(val):
                return float(val)
        # Try backward
        if target_sec - offset >= 0:
            val = prices[target_sec - offset]
            if not np.isnan(val):
                return float(val)

    return None


class S6Strategy(BaseStrategy):
    """S6 Strategy: Streak/Sequence — exploit consecutive same-direction moves

    Divides elapsed time into fixed-size windows, calculates price direction
    for each window, counts consecutive same-direction windows, and enters
    contrarian when streak length reaches threshold.

    Example: If price rises in windows 1, 2, 3, 4 (streak of 4 rising windows),
    enter Down on window 5 (mean reversion bet).

    Note: This is a simplified intra-market version that detects consecutive
    same-direction price moves within one market. The original streak strategy
    tracked consecutive same-outcome markets across sequential markets, which
    requires cross-market state and cannot be implemented within the pure
    function contract. True cross-market streak detection would require the
    backtest runner to track streaks and inject state via snapshot.metadata.
    """

    config: S6Config

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect a trading signal from the market snapshot.

        Contract:
        - Pure function: no side effects, no async, no database access.
        - Return a ``Signal`` when entry conditions are met, ``None`` otherwise.
        - Never raise on NaN-heavy, flat, or insufficient data — just return None.
        """
        prices = snapshot.prices
        total_seconds = snapshot.total_seconds
        cfg = self.config

        # Calculate number of windows
        num_windows = total_seconds // cfg.window_size
        if num_windows < cfg.min_windows:
            return None  # Insufficient data

        # Build window direction list
        directions = []
        for i in range(num_windows):
            start_sec = i * cfg.window_size
            end_sec = (i + 1) * cfg.window_size - 1
            start_price = _get_price(prices, start_sec)
            end_price = _get_price(prices, end_sec)

            if start_price is None or end_price is None:
                directions.append('unknown')
                continue

            delta = end_price - start_price
            if delta > cfg.min_move_threshold:
                directions.append('up')
            elif delta < -cfg.min_move_threshold:
                directions.append('down')
            else:
                directions.append('flat')

        # Scan directions list for consecutive streaks
        current_streak = 0
        streak_direction = None

        for i, d in enumerate(directions):
            if d in ['up', 'down']:
                if d == streak_direction:
                    current_streak += 1
                else:
                    current_streak = 1
                    streak_direction = d

                if current_streak >= cfg.streak_length:
                    # Enter contrarian on next window
                    entry_second = (i + 1) * cfg.window_size
                    if entry_second >= total_seconds:
                        return None  # No room for entry after streak

                    entry_price = _get_price(prices, entry_second)
                    if entry_price is None:
                        return None

                    # Contrarian: if streak is 'up', bet Down
                    direction = 'Down' if streak_direction == 'up' else 'Up'
                    entry_price_final = (1.0 - entry_price) if direction == 'Down' else entry_price
                    entry_price_final = max(0.01, min(0.99, entry_price_final))

                    return Signal(
                        direction=direction,
                        strategy_name=cfg.strategy_name,
                        entry_price=entry_price_final,
                        signal_data={
                            'entry_second': entry_second,
                            'streak_direction': streak_direction,
                            'streak_length': current_streak,
                            'window_size': cfg.window_size,
                        }
                    )
            else:
                # 'flat' or 'unknown' breaks the streak
                current_streak = 0
                streak_direction = None

        return None
