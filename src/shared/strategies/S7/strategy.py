"""S7 Strategy: Composite Ensemble — enter only when 2+ patterns agree on direction.

This strategy runs multiple detection patterns inline (calibration, momentum,
volatility) and returns a signal only when ≥ min_agreement patterns agree.

Note: This strategy duplicates detection logic from S1 (calibration),
S2 (momentum), and S4 (volatility) inline rather than calling those
strategies. The pure function contract prevents accessing the registry
or calling other strategies. If S1/S2/S4 logic changes, this strategy
must be updated manually. A future refactoring could extract shared
detection functions into a utility module.
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S7.config import S7Config


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


class S7Strategy(BaseStrategy):
    """S7 Strategy: Composite Ensemble — enter only when 2+ strategies agree

    Entry logic: Run multiple detection patterns (calibration, momentum, volatility)
    inline and return signal only when ≥ min_agreement patterns agree on direction.
    
    Detection patterns:
    - Calibration (S1): Price deviates from 0.50
    - Momentum (S2): Velocity between 30s-60s exceeds threshold
    - Volatility (S4): High std dev + extreme price
    
    Note: This strategy duplicates detection logic from S1 (calibration),
    S2 (momentum), and S4 (volatility) inline rather than calling those
    strategies. The pure function contract prevents accessing the registry
    or calling other strategies. If S1/S2/S4 logic changes, this strategy
    must be updated manually. A future refactoring could extract shared
    detection functions into a utility module.
    """

    config: S7Config

    # ── private detection methods ────────────────────────────────────

    def _detect_calibration(self, snapshot: MarketSnapshot) -> tuple[str, float] | None:
        """Detect calibration mispricing pattern (from S1).
        
        Returns:
            (direction, confidence) where direction is 'Up' or 'Down', or None
        """
        cfg = self.config
        if not cfg.calibration_enabled:
            return None
        
        prices = snapshot.prices
        
        # Scan window 0 to calibration_eval_window
        window_end = min(cfg.calibration_eval_window, len(prices))
        for sec in range(window_end):
            price = _get_price(prices, sec)
            if price is None:
                continue
            
            # If price < 0.50 - deviation, bet Up
            if price < (0.50 - cfg.calibration_deviation):
                return ('Up', 1.0)
            
            # If price > 0.50 + deviation, bet Down
            if price > (0.50 + cfg.calibration_deviation):
                return ('Down', 1.0)
        
        return None

    def _detect_momentum(self, snapshot: MarketSnapshot) -> tuple[str, float] | None:
        """Detect momentum pattern (from S2).
        
        Returns:
            (direction, confidence) where direction is 'Up' or 'Down', or None
        """
        cfg = self.config
        if not cfg.momentum_enabled:
            return None
        
        prices = snapshot.prices
        
        # Need enough data to reach eval_end
        if len(prices) < cfg.momentum_eval_end:
            return None
        
        p30 = _get_price(prices, cfg.momentum_eval_start, tolerance=10)
        p60 = _get_price(prices, cfg.momentum_eval_end, tolerance=10)
        
        if p30 is None or p60 is None:
            return None
        
        velocity = (p60 - p30) / (cfg.momentum_eval_end - cfg.momentum_eval_start)
        
        # Contrarian to upward momentum
        if velocity >= cfg.momentum_threshold:
            return ('Down', 1.0)
        
        # Contrarian to downward momentum
        if velocity <= -cfg.momentum_threshold:
            return ('Up', 1.0)
        
        return None

    def _detect_volatility(self, snapshot: MarketSnapshot) -> tuple[str, float] | None:
        """Detect volatility regime pattern (from S4).
        
        Returns:
            (direction, confidence) where direction is 'Up' or 'Down', or None
        """
        cfg = self.config
        if not cfg.volatility_enabled:
            return None
        
        # Need to reach eval_sec
        if snapshot.elapsed_seconds < cfg.volatility_eval_sec:
            return None
        
        prices = snapshot.prices
        
        # Calculate volatility over lookback window
        window_start = max(0, cfg.volatility_eval_sec - cfg.volatility_lookback)
        window_prices = prices[window_start:cfg.volatility_eval_sec + 1]
        
        # Filter to valid prices
        valid_prices = window_prices[~np.isnan(window_prices)]
        
        if len(valid_prices) < 10:
            return None
        
        std_dev = float(np.std(valid_prices))
        
        # Check if volatility is high
        if std_dev < cfg.volatility_threshold:
            return None
        
        # Get current price at eval_sec
        current_price = _get_price(prices, cfg.volatility_eval_sec)
        if current_price is None:
            return None
        
        # High vol + extreme low → bet Up
        if current_price <= cfg.extreme_price_low:
            return ('Up', 1.0)
        
        # High vol + extreme high → bet Down
        if current_price >= cfg.extreme_price_high:
            return ('Down', 1.0)
        
        return None

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect a trading signal from the market snapshot.

        Contract:
        - Pure function: no side effects, no async, no database access.
        - Return a ``Signal`` when entry conditions are met, ``None`` otherwise.
        - Never raise on NaN-heavy, flat, or insufficient data — just return None.
        
        Voting logic:
        - Run all enabled detection patterns
        - Count votes by direction (Up vs Down)
        - Return signal only if ≥ min_agreement patterns agree on direction
        """
        cfg = self.config
        
        # Collect signals from all enabled patterns
        detections = []
        
        cal_result = self._detect_calibration(snapshot)
        if cal_result is not None:
            detections.append(cal_result)
        
        mom_result = self._detect_momentum(snapshot)
        if mom_result is not None:
            detections.append(mom_result)
        
        vol_result = self._detect_volatility(snapshot)
        if vol_result is not None:
            detections.append(vol_result)
        
        # Count votes by direction
        up_votes = sum(1 for d, _ in detections if d == 'Up')
        down_votes = sum(1 for d, _ in detections if d == 'Down')
        
        # Check if min_agreement met
        if up_votes >= cfg.min_agreement:
            direction = 'Up'
        elif down_votes >= cfg.min_agreement:
            direction = 'Down'
        else:
            return None  # no consensus
        
        # Calculate entry_second as representative entry point
        # Use momentum eval_end (60s) as canonical entry time
        entry_second = cfg.momentum_eval_end
        entry_price = _get_price(snapshot.prices, entry_second)
        if entry_price is None:
            return None
        
        # Adjust for direction
        if direction == 'Down':
            entry_price = 1.0 - entry_price
        
        entry_price = max(0.01, min(0.99, entry_price))
        
        return Signal(
            direction=direction,
            strategy_name=cfg.strategy_name,
            entry_price=entry_price,
            signal_data={
                'entry_second': entry_second,
                'up_votes': up_votes,
                'down_votes': down_votes,
                'detections': len(detections),
            },
        )
