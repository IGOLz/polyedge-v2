"""S8 Strategy: opening range breakout continuation."""

from __future__ import annotations

import numpy as np

from shared.strategies.S8.config import S8Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import get_price, valid_points


class S8Strategy(BaseStrategy):
    """Follow decisive breaks from an early balance range."""

    config: S8Config

    def _is_confirmed_break(
        self,
        prices: np.ndarray,
        sec: int,
        threshold: float,
        is_up_break: bool,
    ) -> bool:
        confirm_start = sec - self.config.confirmation_points + 1
        for confirm_sec in range(confirm_start, sec + 1):
            price = get_price(prices, confirm_sec, tolerance=2)
            if price is None:
                return False
            if is_up_break and price < threshold:
                return False
            if not is_up_break and price > threshold:
                return False
        return True

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config

        if cfg.breakout_scan_start <= cfg.setup_window_end:
            return None

        setup_points = valid_points(prices, 0, cfg.setup_window_end)
        if len(setup_points) < 6:
            return None

        setup_values = np.array([price for _, price in setup_points], dtype=float)
        range_high = float(np.max(setup_values))
        range_low = float(np.min(setup_values))
        range_width = range_high - range_low

        if range_width < cfg.min_range_width or range_width > cfg.max_range_width:
            return None

        scan_start = max(cfg.breakout_scan_start, cfg.setup_window_end + 1)
        scan_end = min(cfg.breakout_scan_end, len(prices) - 1)

        up_threshold = range_high + cfg.breakout_buffer
        down_threshold = range_low - cfg.breakout_buffer

        for sec in range(scan_start, scan_end + 1):
            price = get_price(prices, sec, tolerance=2)
            if price is None:
                continue

            if abs(price - 0.50) < cfg.min_distance_from_mid:
                continue

            if price >= up_threshold and self._is_confirmed_break(prices, sec, up_threshold, True):
                return Signal(
                    direction="Up",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, price)),
                    signal_data={
                        "entry_second": sec,
                        "range_high": range_high,
                        "range_low": range_low,
                        "range_width": range_width,
                    },
                )

            if price <= down_threshold and self._is_confirmed_break(prices, sec, down_threshold, False):
                return Signal(
                    direction="Down",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, 1.0 - price)),
                    signal_data={
                        "entry_second": sec,
                        "range_high": range_high,
                        "range_low": range_low,
                        "range_width": range_width,
                    },
                )

        return None
