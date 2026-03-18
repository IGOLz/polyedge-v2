"""S9 Strategy: compression breakout continuation."""

from __future__ import annotations

import numpy as np

from shared.strategies.S9.config import S9Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price, path_efficiency, trailing_points, valid_points


class S9Strategy(BaseStrategy):
    """Follow breakouts that emerge from an early low-volatility compression."""

    config: S9Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec < max(cfg.trigger_scan_start, cfg.compression_window + 1, cfg.momentum_lookback):
            return None
        if sec > cfg.trigger_scan_end:
            return None

        compression_points = valid_points(prices, 0, min(cfg.compression_window, sec - 1))
        if len(compression_points) < 8:
            return None

        compression_values = np.array([price for _, price in compression_points], dtype=float)
        compression_std = float(np.std(compression_values))
        compression_high = float(np.max(compression_values))
        compression_low = float(np.min(compression_values))
        compression_range = compression_high - compression_low

        if compression_std > cfg.compression_max_std or compression_range > cfg.compression_max_range:
            return None

        price = get_price(prices, sec, tolerance=1)
        if price is None:
            return None

        momentum_points = trailing_points(prices, sec, cfg.momentum_lookback + 1)
        if len(momentum_points) < 4:
            return None

        momentum_values = np.array([point_price for _, point_price in momentum_points], dtype=float)
        recent_net_move = float(momentum_values[-1] - momentum_values[0])
        recent_efficiency = path_efficiency(momentum_values)
        if recent_efficiency < cfg.efficiency_min:
            return None

        if price >= compression_high + cfg.breakout_distance and recent_net_move >= cfg.breakout_distance:
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": price,
                    "compression_std": compression_std,
                    "compression_range": compression_range,
                    "recent_efficiency": recent_efficiency,
                },
            )

        if price <= compression_low - cfg.breakout_distance and recent_net_move <= -cfg.breakout_distance:
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": price,
                    "compression_std": compression_std,
                    "compression_range": compression_range,
                    "recent_efficiency": recent_efficiency,
                },
            )

        return None
