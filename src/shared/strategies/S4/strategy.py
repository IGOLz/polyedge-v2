"""S4 Strategy: volatility exhaustion fade."""

from __future__ import annotations

import numpy as np

from shared.strategies.S4.config import S4Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import (
    current_second,
    get_price,
    realized_volatility,
    trailing_net_move,
    trailing_values,
)


class S4Strategy(BaseStrategy):
    """Fade extremes only when volatility is high and the latest move stalls."""

    config: S4Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.eval_second:
            return None

        values = trailing_values(prices, sec, cfg.lookback_window)
        if len(values) < 8:
            return None

        vol = realized_volatility(values)
        if vol < cfg.vol_threshold:
            return None

        price = get_price(prices, sec, tolerance=2)
        if price is None:
            return None

        recent_move = trailing_net_move(prices, sec, cfg.reversal_lookback)
        if recent_move is None:
            return None

        if price <= cfg.extreme_price_low and recent_move >= cfg.reversal_min_move:
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": price,
                    "volatility": vol,
                    "recent_move": recent_move,
                },
            )

        if price >= cfg.extreme_price_high and recent_move <= -cfg.reversal_min_move:
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": price,
                    "volatility": vol,
                    "recent_move": recent_move,
                },
            )

        return None
