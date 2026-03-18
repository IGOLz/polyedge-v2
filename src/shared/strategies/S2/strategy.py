"""S2: Volatility strategy.

Detects calibrated volatility at a fixed evaluation second and enters a
contrarian position when spread and volatility conditions are met.  Ported
from trading/strategies.py::evaluate_m4_signal() — logic only, no imports
from that module.
"""

from __future__ import annotations

import numpy as np

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.S2.config import S2Config


class S2Strategy(BaseStrategy):
    """Volatility-based signal detector."""

    config: S2Config

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect calibrated volatility at eval_second → contrarian entry.

        Returns a :class:`Signal` when all conditions are met, otherwise
        *None*.  Never raises on NaN-heavy or flat data.
        """
        prices = snapshot.prices
        cfg = self.config

        # Guard: need enough data past eval_second
        if len(prices) <= cfg.eval_second:
            return None

        # Step 1: get price at eval_second, reject NaN
        price = float(prices[cfg.eval_second])
        if np.isnan(price):
            return None

        # Step 2: base deviation filter — price must deviate from 0.50
        if abs(price - 0.50) < cfg.base_deviation:
            return None

        # Step 3: spread filter — must be within [min_spread, max_spread]
        spread = abs(2.0 * price - 1.0)
        if spread < cfg.min_spread or spread > cfg.max_spread:
            return None

        # Step 4: volatility calculation over the window ending at eval_second
        vol_start = cfg.eval_second - cfg.volatility_window_seconds
        vol_end = cfg.eval_second + 1  # inclusive of eval_second
        vol_slice = prices[vol_start:vol_end]

        # Filter NaN values; need at least 2 valid data points
        valid_values = vol_slice[~np.isnan(vol_slice)]
        if len(valid_values) < 2:
            return None

        volatility = float(np.nanstd(vol_slice))  # ddof=0 (population std)

        # Step 5: volatility threshold check
        if volatility < cfg.volatility_threshold:
            return None

        # Step 6: contrarian direction
        if price > 0.50:
            direction = "Down"
            entry_price = 1.0 - price
        else:
            direction = "Up"
            entry_price = price

        # Build signal with strategy-specific detection metadata
        return Signal(
            direction=direction,
            strategy_name=cfg.strategy_name,
            entry_price=entry_price,
            signal_data={
                "eval_second": cfg.eval_second,
                "spread": round(spread, 6),
                "volatility": round(volatility, 6),
                "entry_second": cfg.eval_second,
                "price_at_eval": round(price, 6),
            },
        )
