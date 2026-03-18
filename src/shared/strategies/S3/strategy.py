"""S3 Strategy: Mean Reversion — fade early spikes after partial reversion.

Entry logic: Two-phase detection:
1. Spike detection: Scan first N seconds for price spike (UP >= threshold or DOWN >= threshold)
2. Reversion wait: After spike, wait for price to revert by >= reversal_pct from peak
3. Enter contrarian: If spike was Up, enter Down; if spike was Down, enter Up
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S3.config import S3Config


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


class S3Strategy(BaseStrategy):
    """S3 Strategy: Mean Reversion — fade early spikes after partial reversion

    Entry logic:
    1. Phase 1 (Spike detection): Scan first spike_lookback seconds for price spike
       - Up spike: UP price >= spike_threshold
       - Down spike: DOWN price >= spike_threshold (UP price <= 1-spike_threshold)
    2. Phase 2 (Reversion wait): After spike, scan min_reversion_sec for reversion
       - Up spike reversion: price drops >= reversion_pct from peak
       - Down spike reversion: price rises >= reversion_pct from trough
    3. Enter contrarian: If Up spike, bet Down; if Down spike, bet Up
    """

    config: S3Config

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect mean reversion signal from market snapshot.

        Contract:
        - Pure function: no side effects, no async, no database access.
        - Return a ``Signal`` when entry conditions are met, ``None`` otherwise.
        - Never raise on NaN-heavy, flat, or insufficient data — just return None.
        """
        prices = snapshot.prices
        cfg = self.config

        # Guard: need enough data for spike lookback
        if len(prices) < cfg.spike_lookback:
            return None

        # ── Phase 1: Spike detection ──

        # Collect valid (non-NaN) prices in spike lookback window
        spike_window = prices[:cfg.spike_lookback]
        valid_prices = []
        valid_indices = []
        
        for i in range(len(spike_window)):
            if not np.isnan(spike_window[i]):
                valid_prices.append(float(spike_window[i]))
                valid_indices.append(i)
        
        if len(valid_prices) == 0:
            return None
        
        valid_prices = np.array(valid_prices)
        valid_indices = np.array(valid_indices)

        # Check for Up spike: max UP price >= spike_threshold
        max_price = np.max(valid_prices)
        if max_price >= cfg.spike_threshold:
            spike_dir = 'Up'
            peak_idx = valid_indices[np.argmax(valid_prices)]
            peak_sec = int(peak_idx)
            peak_price = float(max_price)
        else:
            # Check for Down spike: min UP price <= (1 - spike_threshold)
            min_price = np.min(valid_prices)
            if min_price <= (1.0 - cfg.spike_threshold):
                spike_dir = 'Down'
                peak_idx = valid_indices[np.argmin(valid_prices)]
                peak_sec = int(peak_idx)
                peak_price = float(min_price)  # trough price for Down spike
            else:
                # No spike detected
                return None

        # ── Phase 2: Reversion wait ──

        # Scan from peak_sec+1 to peak_sec+min_reversion_sec for reversion
        reversion_end = min(peak_sec + cfg.min_reversion_sec, len(prices))
        
        for sec in range(peak_sec + 1, reversion_end):
            price = _get_price(prices, sec, tolerance=5)
            if price is None:
                continue
            
            if spike_dir == 'Up':
                # Up spike: wait for price to drop from peak
                reversion_amount = (peak_price - price) / peak_price
                if reversion_amount >= cfg.reversion_pct:
                    # Enter Down (contrarian to Up spike)
                    entry_price = max(0.01, min(0.99, 1.0 - price))  # clamp
                    return Signal(
                        direction="Down",
                        strategy_name=cfg.strategy_name,
                        entry_price=entry_price,
                        signal_data={
                            "entry_second": sec,
                            "spike_direction": spike_dir,
                            "peak_second": peak_sec,
                            "peak_price": peak_price,
                            "reversion_amount": reversion_amount,
                        },
                    )
            
            else:  # spike_dir == 'Down'
                # Down spike: wait for price to rise from trough
                # reversion_amount = (price - peak_price) / (1.0 - peak_price)
                if (1.0 - peak_price) > 0:
                    reversion_amount = (price - peak_price) / (1.0 - peak_price)
                else:
                    reversion_amount = 0
                
                if reversion_amount >= cfg.reversion_pct:
                    # Enter Up (contrarian to Down spike)
                    entry_price = max(0.01, min(0.99, price))  # clamp
                    return Signal(
                        direction="Up",
                        strategy_name=cfg.strategy_name,
                        entry_price=entry_price,
                        signal_data={
                            "entry_second": sec,
                            "spike_direction": spike_dir,
                            "peak_second": peak_sec,
                            "peak_price": peak_price,
                            "reversion_amount": reversion_amount,
                        },
                    )
        
        # No reversion detected within min_reversion_sec window
        return None
