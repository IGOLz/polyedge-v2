"""S10 Strategy: pullback continuation."""

from __future__ import annotations

import numpy as np

from shared.strategies.S10.config import S10Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import get_price, path_efficiency, valid_points


class S10Strategy(BaseStrategy):
    """Follow strong impulses after a shallow pullback and re-acceleration."""

    config: S10Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config

        if cfg.impulse_end <= cfg.impulse_start:
            return None

        impulse_points = valid_points(prices, cfg.impulse_start, cfg.impulse_end)
        if len(impulse_points) < 6:
            return None

        impulse_values = np.array([price for _, price in impulse_points], dtype=float)
        impulse_efficiency = path_efficiency(impulse_values)
        if impulse_efficiency < cfg.impulse_efficiency_min:
            return None

        start_price = impulse_values[0]
        end_price = impulse_values[-1]
        net_move = float(end_price - start_price)

        if abs(net_move) < cfg.impulse_threshold:
            return None

        if net_move > 0:
            return self._evaluate_uptrend(prices, impulse_points, start_price, cfg, impulse_efficiency)

        return self._evaluate_downtrend(prices, impulse_points, start_price, cfg, impulse_efficiency)

    def _evaluate_uptrend(
        self,
        prices: np.ndarray,
        impulse_points: list[tuple[int, float]],
        start_price: float,
        cfg: S10Config,
        impulse_efficiency: float,
    ) -> Signal | None:
        peak_sec, peak_price = max(impulse_points, key=lambda item: item[1])
        impulse_size = peak_price - start_price
        if impulse_size <= 0:
            return None

        scan_end = min(peak_sec + cfg.retrace_window, len(prices) - 1)
        pullback_active = False
        pullback_low = peak_price

        for sec in range(peak_sec + 1, scan_end + 1):
            price = get_price(prices, sec, tolerance=2)
            if price is None:
                continue

            retrace_fraction = (peak_price - price) / impulse_size
            if not pullback_active:
                if cfg.retrace_min <= retrace_fraction <= cfg.retrace_max:
                    pullback_active = True
                    pullback_low = price
                continue

            if retrace_fraction > cfg.retrace_max:
                return None

            pullback_low = min(pullback_low, price)
            if price - pullback_low >= cfg.reacceleration_threshold and price > start_price:
                return Signal(
                    direction="Up",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, price)),
                    signal_data={
                        "entry_second": sec,
                        "impulse_size": impulse_size,
                        "impulse_efficiency": impulse_efficiency,
                        "peak_second": peak_sec,
                    },
                )

        return None

    def _evaluate_downtrend(
        self,
        prices: np.ndarray,
        impulse_points: list[tuple[int, float]],
        start_price: float,
        cfg: S10Config,
        impulse_efficiency: float,
    ) -> Signal | None:
        trough_sec, trough_price = min(impulse_points, key=lambda item: item[1])
        impulse_size = start_price - trough_price
        if impulse_size <= 0:
            return None

        scan_end = min(trough_sec + cfg.retrace_window, len(prices) - 1)
        pullback_active = False
        pullback_high = trough_price

        for sec in range(trough_sec + 1, scan_end + 1):
            price = get_price(prices, sec, tolerance=2)
            if price is None:
                continue

            retrace_fraction = (price - trough_price) / impulse_size
            if not pullback_active:
                if cfg.retrace_min <= retrace_fraction <= cfg.retrace_max:
                    pullback_active = True
                    pullback_high = price
                continue

            if retrace_fraction > cfg.retrace_max:
                return None

            pullback_high = max(pullback_high, price)
            if pullback_high - price >= cfg.reacceleration_threshold and price < start_price:
                return Signal(
                    direction="Down",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, 1.0 - price)),
                    signal_data={
                        "entry_second": sec,
                        "impulse_size": impulse_size,
                        "impulse_efficiency": impulse_efficiency,
                        "trough_second": trough_sec,
                    },
                )

        return None
