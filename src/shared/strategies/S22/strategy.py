"""S22 Strategy: SessionBand-style late price-band continuation."""

from __future__ import annotations

from shared.strategies.S22.config import S22Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import (
    current_second,
    get_feature_value,
    get_price,
    get_window_feature_value,
)


class S22Strategy(BaseStrategy):
    """Enter only in the final tau window and only inside a tight price band."""

    config: S22Config

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
        if sec < 0:
            return None

        remaining_seconds = snapshot.total_seconds - 1 - sec
        if remaining_seconds > cfg.max_seconds_to_close or remaining_seconds < cfg.min_seconds_to_close:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        underlying_return_open = get_feature_value(snapshot, "underlying_return_from_market_open", sec)
        market_delta_open = get_feature_value(snapshot, "market_up_delta_from_market_open", sec)
        recent_return = get_window_feature_value(snapshot, "underlying_return", 5, sec)
        trade_count = get_feature_value(snapshot, "underlying_trade_count", sec)
        if (
            up_price is None
            or underlying_return_open is None
            or market_delta_open is None
            or recent_return is None
            or trade_count is None
        ):
            return None

        lead_abs = abs(underlying_return_open)
        if lead_abs < cfg.min_lead_return_from_open or lead_abs > cfg.max_lead_return_from_open:
            return None

        direction_sign = 1 if underlying_return_open > 0 else -1 if underlying_return_open < 0 else 0
        if direction_sign == 0:
            return None
        if direction_sign * recent_return < cfg.min_recent_return_5s:
            return None
        if direction_sign * market_delta_open < cfg.min_market_delta_from_open:
            return None
        if trade_count < cfg.min_trade_count:
            return None

        token_price = up_price if direction_sign > 0 else 1.0 - up_price
        token_price = max(0.01, min(0.99, token_price))
        if token_price < cfg.entry_price_floor or token_price > cfg.entry_price_cap:
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
                "underlying_return_5s": recent_return,
                "market_delta_from_open": market_delta_open,
                "trade_count": trade_count,
                "lead_abs": lead_abs,
            },
        )
