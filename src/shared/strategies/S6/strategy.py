"""S6 Strategy: prior-market streak fade."""

from __future__ import annotations

from shared.strategies.S6.config import S6Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price


class S6Strategy(BaseStrategy):
    """Fade streaks of resolved outcomes in the same market type."""

    config: S6Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        streak_direction = snapshot.metadata.get("prior_market_type_streak_direction")
        streak_length = int(snapshot.metadata.get("prior_market_type_streak_length", 0) or 0)
        if streak_direction not in {"Up", "Down"}:
            return None
        if streak_length < cfg.streak_length:
            return None

        if cfg.streak_direction_filter != "both" and streak_direction != cfg.streak_direction_filter:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=2)
        if up_price is None:
            return None
        if not (cfg.price_floor <= up_price <= cfg.price_ceiling):
            return None

        direction = "Down" if streak_direction == "Up" else "Up"
        entry_price = up_price if direction == "Up" else 1.0 - up_price

        return Signal(
            direction=direction,
            strategy_name=cfg.strategy_name,
            entry_price=max(0.01, min(0.99, entry_price)),
            signal_data={
                "entry_second": sec,
                "observed_up_price": up_price,
                "prior_streak_direction": streak_direction,
                "prior_streak_length": streak_length,
            },
        )
