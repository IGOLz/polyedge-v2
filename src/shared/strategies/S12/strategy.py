"""S12 Strategy: late trend confirmation."""

from __future__ import annotations

import numpy as np

from shared.strategies.S12.config import S12Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, direction_flips, get_price, path_efficiency, trailing_points


class S12Strategy(BaseStrategy):
    """Follow clean late-stage trends when the path is decisive."""

    config: S12Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        phase_start = int(snapshot.total_seconds * cfg.late_phase_start_pct)
        if sec < max(phase_start, cfg.lookback_seconds):
            return None
        if sec > snapshot.total_seconds - cfg.min_remaining_seconds - 1:
            return None

        window_points = trailing_points(prices, sec, cfg.lookback_seconds + 1)
        if len(window_points) < 6:
            return None

        window_values = np.array([price for _, price in window_points], dtype=float)
        current_price = float(window_values[-1])
        net_move = float(window_values[-1] - window_values[0])
        if abs(net_move) < cfg.net_move_threshold:
            return None
        if abs(current_price - 0.50) < cfg.min_price_distance_from_mid:
            return None

        efficiency = path_efficiency(window_values)
        if efficiency < cfg.efficiency_min:
            return None

        flip_count = direction_flips(window_values)
        if flip_count > cfg.max_flip_count:
            return None

        if net_move > 0 and current_price > 0.50:
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, current_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": current_price,
                    "efficiency": efficiency,
                    "flip_count": flip_count,
                    "net_move": net_move,
                },
            )

        if net_move < 0 and current_price < 0.50:
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - current_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": current_price,
                    "efficiency": efficiency,
                    "flip_count": flip_count,
                    "net_move": net_move,
                },
            )

        return None
