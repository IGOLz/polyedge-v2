"""S2 Strategy: early momentum continuation."""

from __future__ import annotations

import numpy as np

from shared.strategies.S2.config import S2Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price, path_efficiency, trailing_points


class S2Strategy(BaseStrategy):
    """Follow efficient directional moves instead of fading them blindly."""

    config: S2Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.eval_window_end or sec > cfg.max_entry_second:
            return None

        lookback = max(1, cfg.eval_window_end - cfg.eval_window_start)
        points = trailing_points(prices, sec, lookback + 1)
        if len(points) < 4:
            return None

        values = np.array([price for _, price in points], dtype=float)
        net_move = float(values[-1] - values[0])
        if abs(net_move) < cfg.momentum_threshold:
            return None

        efficiency = path_efficiency(values)
        if efficiency < cfg.efficiency_min:
            return None

        price = get_price(prices, sec, tolerance=cfg.tolerance)
        if price is None or abs(price - 0.50) < cfg.min_distance_from_mid:
            return None

        direction = "Up" if net_move > 0 else "Down"
        entry_price = price if direction == "Up" else 1.0 - price

        return Signal(
            direction=direction,
            strategy_name=cfg.strategy_name,
            entry_price=max(0.01, min(0.99, entry_price)),
            signal_data={
                "entry_second": sec,
                "observed_up_price": price,
                "net_move": net_move,
                "efficiency": efficiency,
            },
        )
