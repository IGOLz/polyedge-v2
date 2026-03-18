"""S3 Strategy: spike mean reversion."""

from __future__ import annotations

import numpy as np

from shared.strategies.S3.config import S3Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price, valid_points


class S3Strategy(BaseStrategy):
    """Fade sharp spikes only after the reversion is visible now."""

    config: S3Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec <= 0:
            return None

        current_price = get_price(prices, sec, tolerance=2)
        if current_price is None:
            return None

        window_start = max(0, sec - (cfg.spike_lookback + cfg.min_reversion_sec))
        points = valid_points(prices, window_start, sec - 1)
        if len(points) < 6:
            return None

        peak_sec, peak_price = max(points, key=lambda item: item[1])
        trough_sec, trough_price = min(points, key=lambda item: item[1])

        candidates: list[tuple[str, float, int, float]] = []

        if peak_price >= cfg.spike_threshold and 0 < sec - peak_sec <= cfg.min_reversion_sec:
            reversion_amount = (peak_price - current_price) / peak_price if peak_price > 0 else 0.0
            if reversion_amount >= cfg.reversion_pct and current_price < peak_price and current_price > 0.50:
                candidates.append(("Down", reversion_amount, peak_sec, peak_price))

        if trough_price <= (1.0 - cfg.spike_threshold) and 0 < sec - trough_sec <= cfg.min_reversion_sec:
            denom = 1.0 - trough_price
            reversion_amount = (current_price - trough_price) / denom if denom > 0 else 0.0
            if reversion_amount >= cfg.reversion_pct and current_price > trough_price and current_price < 0.50:
                candidates.append(("Up", reversion_amount, trough_sec, trough_price))

        if not candidates:
            return None

        direction, reversion_amount, extremum_sec, extremum_price = max(
            candidates,
            key=lambda item: item[1],
        )
        entry_price = current_price if direction == "Up" else 1.0 - current_price

        return Signal(
            direction=direction,
            strategy_name=cfg.strategy_name,
            entry_price=max(0.01, min(0.99, entry_price)),
            signal_data={
                "entry_second": sec,
                "observed_up_price": current_price,
                "extremum_second": extremum_sec,
                "extremum_price": extremum_price,
                "reversion_amount": reversion_amount,
            },
        )
