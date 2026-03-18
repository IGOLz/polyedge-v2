"""S1: Spike Reversion strategy.

Detects a price spike in the early seconds of a market, waits for partial
reversion, then enters a contrarian position.  Ported from
analysis/backtest/module_3_mean_reversion.py — logic only, no imports from
that module.
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S1.config import S1Config


class S1Strategy(BaseStrategy):
    """Spike-reversion signal detector."""

    config: S1Config

    # ── internal helpers ────────────────────────────────────────────

    def _find_spike(
        self,
        prices: np.ndarray,
    ) -> tuple[str, int, float] | None:
        """Scan first *spike_detection_window_seconds* for a spike.

        Returns ``(spike_direction, peak_second, peak_price)`` or *None*.

        * ``'Up'``  — up-price spiked high  (>= spike_threshold_up)
        * ``'Down'`` — up-price dropped low, i.e. down-price spiked
                       (``1 - min_price >= spike_threshold_down`` equivalent
                        rewritten as ``min_price <= 1 - spike_threshold_down``)
        """
        cfg = self.config
        window = prices[: cfg.spike_detection_window_seconds]
        valid_mask = ~np.isnan(window)
        if not np.any(valid_mask):
            return None

        valid_prices = window[valid_mask]
        valid_indices = np.where(valid_mask)[0]

        # Up-spike: up_price ≥ threshold_up
        max_price = float(np.max(valid_prices))
        if max_price >= cfg.spike_threshold_up:
            peak_idx = int(valid_indices[np.argmax(valid_prices)])
            return ("Up", peak_idx, max_price)

        # Down-spike: up_price drops so low that (1 - min_price) ≥ spike_threshold_up
        # Original backtest check: ``(1.0 - min_price) >= spike_threshold``
        # spike_threshold_down (0.20) is the *up-price* floor; anything at or
        # below it counts as a down-spike.
        min_price = float(np.min(valid_prices))
        if min_price <= cfg.spike_threshold_down:
            peak_idx = int(valid_indices[np.argmin(valid_prices)])
            return ("Down", peak_idx, min_price)

        return None

    def _find_reversion(
        self,
        prices: np.ndarray,
        spike_direction: str,
        peak_second: int,
        peak_price: float,
    ) -> tuple[int, float, str] | None:
        """After a spike, scan for sufficient reversion.

        Returns ``(reversion_second, entry_price, signal_direction)`` or
        *None*.  ``signal_direction`` is contrarian to the spike.
        """
        cfg = self.config
        total = len(prices)
        end = min(peak_second + cfg.min_reversion_ticks + 1, total)

        for sec in range(peak_second + 1, end):
            price = prices[sec]
            if np.isnan(price):
                continue

            if spike_direction == "Up":
                # Up-price spiked high → wait for it to drop back
                reversion_amount = (peak_price - price) / peak_price
                if reversion_amount >= cfg.reversion_reversal_pct:
                    entry_price = 1.0 - price  # buy DOWN token
                    return (sec, float(entry_price), "Down")
            else:
                # Down-spike (up-price was very low) → wait for recovery
                denominator = 1.0 - peak_price
                if denominator <= 0:
                    continue
                reversion_amount = (price - peak_price) / denominator
                if reversion_amount >= cfg.reversion_reversal_pct:
                    entry_price = price  # buy UP token
                    return (sec, float(entry_price), "Up")

        return None

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect spike → reversion → contrarian entry.

        Returns a :class:`Signal` when all conditions are met, otherwise
        *None*.  Never raises on NaN-heavy or flat data.
        """
        prices = snapshot.prices
        cfg = self.config

        # Guard: need enough data for the detection window
        if len(prices) < cfg.spike_detection_window_seconds:
            return None

        # Step 1: find spike
        spike = self._find_spike(prices)
        if spike is None:
            return None
        spike_direction, peak_second, peak_price = spike

        # Step 2: find reversion
        reversion = self._find_reversion(
            prices, spike_direction, peak_second, peak_price
        )
        if reversion is None:
            return None
        reversion_second, entry_price, signal_direction = reversion

        # Step 3: entry-price filter
        if entry_price > cfg.entry_price_threshold:
            return None

        # Build signal_data with strategy-specific detection metadata
        signal_data: dict = {
            "spike_direction": spike_direction,
            "reversion_price": entry_price,
            "reversion_second": reversion_second,
        }
        if spike_direction == "Up":
            signal_data["spike_max_price"] = peak_price
        else:
            signal_data["spike_min_price"] = peak_price

        return Signal(
            direction=signal_direction,
            strategy_name=cfg.strategy_name,
            entry_price=entry_price,
            signal_data=signal_data,
        )
