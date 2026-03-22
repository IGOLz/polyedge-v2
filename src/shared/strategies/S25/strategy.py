"""S25 Strategy: S20-lite checkpoint drift follow."""

from __future__ import annotations

from shared.strategies.S25.config import S25Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import (
    current_second,
    get_feature_value,
    get_price,
    get_window_feature_value,
)


class S25Strategy(BaseStrategy):
    """Use checkpoint entries, but rely only on readily available 5s features."""

    config: S25Config

    def required_feature_columns(self) -> tuple[str, ...]:
        return (
            "underlying_return_5s",
            "market_up_delta_5s",
            "underlying_trade_count",
        )

    def _checkpoint_hit(self, remaining_seconds: int, duration_minutes: int) -> bool:
        tolerance = self.config.checkpoint_tolerance
        checkpoints = {
            5: (60, 30, 15),
            15: (300, 240, 180),
            60: (900, 600, 300),
            240: (7200, 6300, 5400, 4500, 3600, 2700, 1800, 900),
        }.get(duration_minutes)
        if checkpoints is None:
            return False
        return any(abs(remaining_seconds - checkpoint) <= tolerance for checkpoint in checkpoints)

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < 0:
            return None

        duration_minutes = int(snapshot.metadata.get("duration_minutes", 0) or 0)
        remaining_seconds = snapshot.total_seconds - 1 - sec
        if remaining_seconds < 0 or not self._checkpoint_hit(remaining_seconds, duration_minutes):
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        underlying_return_5s = get_window_feature_value(snapshot, "underlying_return", 5, sec)
        market_delta_5s = get_window_feature_value(snapshot, "market_up_delta", 5, sec)
        trade_count = get_feature_value(snapshot, "underlying_trade_count", sec)
        if (
            up_price is None
            or underlying_return_5s is None
            or market_delta_5s is None
            or trade_count is None
        ):
            return None

        direction_sign = 1 if underlying_return_5s > 0 else -1 if underlying_return_5s < 0 else 0
        if direction_sign == 0:
            return None
        if abs(underlying_return_5s) < cfg.min_underlying_return_5s:
            return None
        if direction_sign * market_delta_5s < cfg.min_market_delta_5s:
            return None
        if trade_count < cfg.min_trade_count:
            return None
        if abs(up_price - 0.50) < cfg.min_price_distance_from_mid:
            return None

        expected_market_delta = cfg.underlying_beta * underlying_return_5s
        directional_gap = direction_sign * (expected_market_delta - market_delta_5s)
        if directional_gap < cfg.min_directional_gap:
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
                "underlying_return_5s": underlying_return_5s,
                "market_delta_5s": market_delta_5s,
                "trade_count": trade_count,
                "expected_market_delta": expected_market_delta,
                "directional_gap": directional_gap,
            },
        )
