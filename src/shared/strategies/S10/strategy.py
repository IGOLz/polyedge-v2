"""S10 Strategy: pullback continuation."""

from __future__ import annotations

import numpy as np

from shared.strategies.S10.config import S10Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price, path_efficiency, valid_points


class S10Strategy(BaseStrategy):
    """Follow strong impulses after a shallow pullback and re-acceleration."""

    config: S10Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec <= cfg.impulse_end:
            return None

        impulse_points = valid_points(prices, cfg.impulse_start, min(cfg.impulse_end, sec - 1))
        if len(impulse_points) < 6:
            return None

        impulse_values = np.array([price for _, price in impulse_points], dtype=float)
        impulse_efficiency = path_efficiency(impulse_values)
        if impulse_efficiency < cfg.impulse_efficiency_min:
            return None

        start_price = float(impulse_values[0])
        end_price = float(impulse_values[-1])
        net_move = end_price - start_price
        if abs(net_move) < cfg.impulse_threshold:
            return None

        if net_move > 0:
            return self._evaluate_uptrend(prices, sec, impulse_points, start_price, cfg, impulse_efficiency)
        return self._evaluate_downtrend(prices, sec, impulse_points, start_price, cfg, impulse_efficiency)

    def _evaluate_uptrend(self, prices, sec, impulse_points, start_price, cfg, impulse_efficiency):
        peak_sec, peak_price = max(impulse_points, key=lambda item: item[1])
        if sec <= peak_sec or sec > peak_sec + cfg.retrace_window:
            return None

        impulse_size = peak_price - start_price
        if impulse_size <= 0:
            return None

        pullback_points = valid_points(prices, peak_sec + 1, sec)
        if len(pullback_points) < 2:
            return None

        pullback_low = min(price for _, price in pullback_points)
        current_price = pullback_points[-1][1]
        retrace_fraction = (peak_price - pullback_low) / impulse_size
        if retrace_fraction < cfg.retrace_min or retrace_fraction > cfg.retrace_max:
            return None
        if current_price - pullback_low < cfg.reacceleration_threshold:
            return None
        if current_price <= start_price:
            return None

        return Signal(
            direction="Up",
            strategy_name=cfg.strategy_name,
            entry_price=max(0.01, min(0.99, current_price)),
            signal_data={
                "entry_second": sec,
                "observed_up_price": current_price,
                "impulse_size": impulse_size,
                "impulse_efficiency": impulse_efficiency,
                "peak_second": peak_sec,
                "stop_loss_price": cfg.live_stop_loss_price,
                "take_profit_price": cfg.live_take_profit_price,
            },
        )

    def _evaluate_downtrend(self, prices, sec, impulse_points, start_price, cfg, impulse_efficiency):
        trough_sec, trough_price = min(impulse_points, key=lambda item: item[1])
        if sec <= trough_sec or sec > trough_sec + cfg.retrace_window:
            return None

        impulse_size = start_price - trough_price
        if impulse_size <= 0:
            return None

        pullback_points = valid_points(prices, trough_sec + 1, sec)
        if len(pullback_points) < 2:
            return None

        pullback_high = max(price for _, price in pullback_points)
        current_price = pullback_points[-1][1]
        retrace_fraction = (pullback_high - trough_price) / impulse_size
        if retrace_fraction < cfg.retrace_min or retrace_fraction > cfg.retrace_max:
            return None
        if pullback_high - current_price < cfg.reacceleration_threshold:
            return None
        if current_price >= start_price:
            return None

        return Signal(
            direction="Down",
            strategy_name=cfg.strategy_name,
            entry_price=max(0.01, min(0.99, 1.0 - current_price)),
            signal_data={
                "entry_second": sec,
                "observed_up_price": current_price,
                "impulse_size": impulse_size,
                "impulse_efficiency": impulse_efficiency,
                "trough_second": trough_sec,
                "stop_loss_price": cfg.live_stop_loss_price,
                "take_profit_price": cfg.live_take_profit_price,
            },
        )
