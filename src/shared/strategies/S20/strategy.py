"""S20 Strategy: EVcurve-style checkpoint continuation."""

from __future__ import annotations

from shared.strategies.S20.config import S20Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import (
    current_second,
    get_feature_value,
    get_price,
    get_window_feature_value,
)


class S20Strategy(BaseStrategy):
    """Follow the underlying at scheduled checkpoint windows when PM still lags."""

    config: S20Config

    def required_feature_columns(self) -> tuple[str, ...]:
        return (
            "underlying_return_from_market_open",
            "market_up_delta_from_market_open",
            "underlying_return_5s",
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
        underlying_return_open = get_feature_value(snapshot, "underlying_return_from_market_open", sec)
        market_delta_open = get_feature_value(snapshot, "market_up_delta_from_market_open", sec)
        recent_return = get_window_feature_value(snapshot, "underlying_return", 5, sec)
        if (
            up_price is None
            or underlying_return_open is None
            or market_delta_open is None
            or recent_return is None
        ):
            return None

        direction_sign = 1 if underlying_return_open > 0 else -1 if underlying_return_open < 0 else 0
        if direction_sign == 0:
            return None
        if abs(underlying_return_open) < cfg.min_underlying_return_from_open:
            return None
        if direction_sign * recent_return < cfg.min_recent_return_5s:
            return None
        if direction_sign * market_delta_open < cfg.min_market_delta_from_open:
            return None

        expected_market_delta = cfg.underlying_beta * underlying_return_open
        directional_gap = direction_sign * (expected_market_delta - market_delta_open)
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
                "underlying_return_from_open": underlying_return_open,
                "underlying_return_5s": recent_return,
                "market_delta_from_open": market_delta_open,
                "expected_market_delta": expected_market_delta,
                "directional_gap": directional_gap,
            },
        )
