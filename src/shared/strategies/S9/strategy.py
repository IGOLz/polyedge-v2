"""S9 Strategy: compression breakout continuation."""

from __future__ import annotations

import numpy as np

from shared.strategies.S9.config import S9Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import get_price, path_efficiency, valid_points


class S9Strategy(BaseStrategy):
    """Follow breakouts that emerge from an early low-volatility compression."""

    config: S9Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config

        if cfg.trigger_scan_start <= cfg.compression_window:
            return None

        compression_points = valid_points(prices, 0, cfg.compression_window)
        if len(compression_points) < 8:
            return None

        compression_values = np.array(
            [price for _, price in compression_points],
            dtype=float,
        )
        compression_std = float(np.std(compression_values))
        compression_high = float(np.max(compression_values))
        compression_low = float(np.min(compression_values))
        compression_range = compression_high - compression_low

        if compression_std > cfg.compression_max_std:
            return None
        if compression_range > cfg.compression_max_range:
            return None

        scan_start = max(cfg.trigger_scan_start, cfg.compression_window + 1, cfg.momentum_lookback)
        scan_end = min(cfg.trigger_scan_end, len(prices) - 1)

        for sec in range(scan_start, scan_end + 1):
            price = get_price(prices, sec, tolerance=2)
            if price is None:
                continue

            momentum_points = valid_points(prices, sec - cfg.momentum_lookback, sec)
            if len(momentum_points) < 4:
                continue

            momentum_values = np.array(
                [point_price for _, point_price in momentum_points],
                dtype=float,
            )
            recent_net_move = float(momentum_values[-1] - momentum_values[0])
            recent_efficiency = path_efficiency(momentum_values)

            if recent_efficiency < cfg.efficiency_min:
                continue

            if (
                price >= compression_high + cfg.breakout_distance
                and recent_net_move >= cfg.breakout_distance
            ):
                return Signal(
                    direction="Up",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, price)),
                    signal_data={
                        "entry_second": sec,
                        "compression_std": compression_std,
                        "compression_range": compression_range,
                        "recent_efficiency": recent_efficiency,
                    },
                )

            if (
                price <= compression_low - cfg.breakout_distance
                and recent_net_move <= -cfg.breakout_distance
            ):
                return Signal(
                    direction="Down",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, 1.0 - price)),
                    signal_data={
                        "entry_second": sec,
                        "compression_std": compression_std,
                        "compression_range": compression_range,
                        "recent_efficiency": recent_efficiency,
                    },
                )

        return None
