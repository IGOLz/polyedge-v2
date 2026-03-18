"""S5 Strategy: time-phase midpoint reclaim."""

from __future__ import annotations

from shared.strategies.S5.config import S5Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price


class S5Strategy(BaseStrategy):
    """Trade midpoint crosses only during the time phases you trust."""

    config: S5Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        current_hour = snapshot.metadata.get("hour")
        if cfg.allowed_hours is not None:
            if not cfg.allowed_hours:
                return None
            if current_hour is not None and current_hour not in cfg.allowed_hours:
                return None

        price = get_price(prices, sec, tolerance=2)
        prev_price = get_price(prices, sec - cfg.approach_lookback, tolerance=2)
        if price is None or prev_price is None:
            return None

        if not (cfg.price_range_low <= price <= cfg.price_range_high):
            return None

        if prev_price <= 0.50 - cfg.cross_buffer and price >= 0.50 + cfg.cross_buffer:
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": price,
                    "previous_up_price": prev_price,
                    "hour": current_hour,
                },
            )

        if prev_price >= 0.50 + cfg.cross_buffer and price <= 0.50 - cfg.cross_buffer:
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": price,
                    "previous_up_price": prev_price,
                    "hour": current_hour,
                },
            )

        return None
