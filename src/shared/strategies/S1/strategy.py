"""S1 Strategy: balanced-mispricing fade."""

from __future__ import annotations

from shared.strategies.S1.config import S1Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price, trailing_net_move


class S1Strategy(BaseStrategy):
    """Fade moves away from 0.50 only after they begin to snap back."""

    config: S1Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        price = get_price(prices, sec, tolerance=2)
        if price is None:
            return None

        recent_move = trailing_net_move(prices, sec, cfg.rebound_lookback)
        if recent_move is None:
            return None

        if price <= cfg.price_low_threshold and (0.50 - price) >= cfg.min_deviation:
            if recent_move >= cfg.rebound_min_move:
                return Signal(
                    direction="Up",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, price)),
                    signal_data={
                        "entry_second": sec,
                        "observed_up_price": price,
                        "recent_move": recent_move,
                    },
                )

        if price >= cfg.price_high_threshold and (price - 0.50) >= cfg.min_deviation:
            if recent_move <= -cfg.rebound_min_move:
                return Signal(
                    direction="Down",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, 1.0 - price)),
                    signal_data={
                        "entry_second": sec,
                        "observed_up_price": price,
                        "recent_move": recent_move,
                    },
                )

        return None
