"""S23 Strategy: EVSnipe-style trigger crossing."""

from __future__ import annotations

from shared.strategies.S23.config import S23Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_feature_value, get_price, get_window_feature_value


class S23Strategy(BaseStrategy):
    """Fire only when the open-to-close return crosses a trigger in real time."""

    config: S23Config

    def required_feature_columns(self) -> tuple[str, ...]:
        return (
            "underlying_return_from_market_open",
            "market_up_delta_from_market_open",
            "underlying_return_5s",
            "underlying_trade_count",
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < max(1, cfg.entry_window_start) or sec > cfg.entry_window_end:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        current_return_open = get_feature_value(snapshot, "underlying_return_from_market_open", sec)
        previous_return_open = get_feature_value(snapshot, "underlying_return_from_market_open", sec - 1)
        market_delta_open = get_feature_value(snapshot, "market_up_delta_from_market_open", sec)
        recent_return = get_window_feature_value(snapshot, "underlying_return", 5, sec)
        trade_count = get_feature_value(snapshot, "underlying_trade_count", sec)
        if (
            up_price is None
            or current_return_open is None
            or previous_return_open is None
            or market_delta_open is None
            or recent_return is None
            or trade_count is None
        ):
            return None

        if trade_count < cfg.min_trade_count:
            return None

        token_price_up = max(0.01, min(0.99, up_price))
        token_price_down = max(0.01, min(0.99, 1.0 - up_price))

        crossed_up = (
            previous_return_open < cfg.trigger_return_from_open
            and previous_return_open >= cfg.trigger_return_from_open - cfg.pre_trigger_buffer
            and current_return_open >= cfg.trigger_return_from_open
            and recent_return >= cfg.min_recent_return_5s
            and 0.0 <= market_delta_open <= cfg.max_market_delta_from_open
            and token_price_up <= cfg.max_entry_price
        )
        if crossed_up:
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=token_price_up,
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "previous_underlying_return_from_open": previous_return_open,
                    "underlying_return_from_open": current_return_open,
                    "underlying_return_5s": recent_return,
                    "market_delta_from_open": market_delta_open,
                    "trade_count": trade_count,
                },
            )

        crossed_down = (
            previous_return_open > -cfg.trigger_return_from_open
            and previous_return_open <= -cfg.trigger_return_from_open + cfg.pre_trigger_buffer
            and current_return_open <= -cfg.trigger_return_from_open
            and recent_return <= -cfg.min_recent_return_5s
            and -cfg.max_market_delta_from_open <= market_delta_open <= 0.0
            and token_price_down <= cfg.max_entry_price
        )
        if crossed_down:
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=token_price_down,
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "previous_underlying_return_from_open": previous_return_open,
                    "underlying_return_from_open": current_return_open,
                    "underlying_return_5s": recent_return,
                    "market_delta_from_open": market_delta_open,
                    "trade_count": trade_count,
                },
            )

        return None
