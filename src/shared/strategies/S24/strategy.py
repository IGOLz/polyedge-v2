"""S24 Strategy: premarket-inspired opening drive accumulation."""

from __future__ import annotations

from shared.strategies.S24.config import S24Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_feature_value, get_price, get_window_feature_value


class S24Strategy(BaseStrategy):
    """Approximate premarket ladder logic with a post-open early accumulation filter."""

    config: S24Config

    def required_feature_columns(self) -> tuple[str, ...]:
        return (
            "underlying_return_from_market_open",
            "market_up_delta_from_market_open",
            "underlying_return_5s",
            "underlying_trade_count",
            "underlying_volume",
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        underlying_return_open = get_feature_value(snapshot, "underlying_return_from_market_open", sec)
        market_delta_open = get_feature_value(snapshot, "market_up_delta_from_market_open", sec)
        recent_return = get_window_feature_value(snapshot, "underlying_return", 5, sec)
        trade_count = get_feature_value(snapshot, "underlying_trade_count", sec)
        volume = get_feature_value(snapshot, "underlying_volume", sec)
        if (
            up_price is None
            or underlying_return_open is None
            or market_delta_open is None
            or recent_return is None
            or trade_count is None
            or volume is None
        ):
            return None

        direction_sign = 1 if underlying_return_open > 0 else -1 if underlying_return_open < 0 else 0
        if direction_sign == 0:
            return None
        if abs(underlying_return_open) < cfg.min_underlying_return_from_open:
            return None
        if direction_sign * recent_return < cfg.min_recent_return_5s:
            return None

        directional_market_delta = direction_sign * market_delta_open
        if directional_market_delta < cfg.min_market_delta_from_open:
            return None
        if directional_market_delta > cfg.max_market_delta_from_open:
            return None
        if trade_count < cfg.min_trade_count or volume < cfg.min_volume:
            return None

        token_price = up_price if direction_sign > 0 else 1.0 - up_price
        token_price = max(0.01, min(0.99, token_price))
        if token_price > cfg.max_entry_price:
            return None

        return Signal(
            direction="Up" if direction_sign > 0 else "Down",
            strategy_name=cfg.strategy_name,
            entry_price=token_price,
            signal_data={
                "entry_second": sec,
                "observed_up_price": up_price,
                "underlying_return_from_open": underlying_return_open,
                "underlying_return_5s": recent_return,
                "market_delta_from_open": market_delta_open,
                "trade_count": trade_count,
                "underlying_volume": volume,
            },
        )
