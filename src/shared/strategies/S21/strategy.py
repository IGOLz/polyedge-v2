"""S21 Strategy: endgame-sweep continuation."""

from __future__ import annotations

from shared.strategies.S21.config import S21Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import (
    current_second,
    get_feature_value,
    get_price,
    get_window_feature_value,
)


class S21Strategy(BaseStrategy):
    """Trade late sweeps only when the open-to-close drift is already established."""

    config: S21Config

    def required_feature_columns(self) -> tuple[str, ...]:
        return (
            "underlying_return_from_market_open",
            "market_up_delta_from_market_open",
            "underlying_return_5s",
            "market_up_delta_5s",
            "underlying_trade_count",
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < 0:
            return None

        remaining_seconds = snapshot.total_seconds - 1 - sec
        if remaining_seconds > cfg.max_seconds_to_close or remaining_seconds < cfg.min_seconds_to_close:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        underlying_return_open = get_feature_value(snapshot, "underlying_return_from_market_open", sec)
        market_delta_open = get_feature_value(snapshot, "market_up_delta_from_market_open", sec)
        underlying_return_5s = get_window_feature_value(snapshot, "underlying_return", 5, sec)
        market_delta_5s = get_window_feature_value(snapshot, "market_up_delta", 5, sec)
        trade_count = get_feature_value(snapshot, "underlying_trade_count", sec)
        if (
            up_price is None
            or underlying_return_open is None
            or market_delta_open is None
            or underlying_return_5s is None
            or market_delta_5s is None
            or trade_count is None
        ):
            return None

        direction_sign = 1 if underlying_return_open > 0 else -1 if underlying_return_open < 0 else 0
        if direction_sign == 0:
            return None
        if abs(underlying_return_open) < cfg.min_underlying_return_from_open:
            return None
        if direction_sign * underlying_return_5s < cfg.min_recent_underlying_return_5s:
            return None
        if direction_sign * market_delta_5s < cfg.min_recent_market_delta_5s:
            return None
        if direction_sign * market_delta_open < cfg.min_market_delta_from_open:
            return None
        if trade_count < cfg.min_trade_count:
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
                "remaining_seconds": remaining_seconds,
                "observed_up_price": up_price,
                "underlying_return_from_open": underlying_return_open,
                "underlying_return_5s": underlying_return_5s,
                "market_delta_from_open": market_delta_open,
                "market_delta_5s": market_delta_5s,
                "trade_count": trade_count,
            },
        )
