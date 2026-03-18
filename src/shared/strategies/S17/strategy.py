"""S17 Strategy: fair-value residual fade."""

from __future__ import annotations

from shared.strategies.S17.config import S17Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_feature_value, get_price


class S17Strategy(BaseStrategy):
    """Fade market overshoots relative to the underlying move from open."""

    config: S17Config

    def required_feature_columns(self) -> tuple[str, ...]:
        return (
            "market_up_delta_from_market_open",
            "underlying_return_from_market_open",
            "market_up_delta_5s",
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        market_delta = get_feature_value(snapshot, "market_up_delta_from_market_open", sec)
        underlying_return = get_feature_value(snapshot, "underlying_return_from_market_open", sec)
        reversal_delta = get_feature_value(snapshot, "market_up_delta_5s", sec)
        if (
            up_price is None
            or market_delta is None
            or underlying_return is None
            or reversal_delta is None
        ):
            return None

        if abs(underlying_return) < cfg.min_underlying_move_abs:
            return None

        expected_market_delta = cfg.underlying_beta * underlying_return
        residual = market_delta - expected_market_delta

        if (
            residual >= cfg.residual_threshold
            and up_price >= cfg.extreme_price_high
            and reversal_delta <= -cfg.reversal_confirmation_abs
        ):
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "market_delta_from_open": market_delta,
                    "underlying_return_from_open": underlying_return,
                    "expected_market_delta": expected_market_delta,
                    "residual": residual,
                    "market_delta_5s": reversal_delta,
                },
            )

        if (
            residual <= -cfg.residual_threshold
            and up_price <= cfg.extreme_price_low
            and reversal_delta >= cfg.reversal_confirmation_abs
        ):
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "market_delta_from_open": market_delta,
                    "underlying_return_from_open": underlying_return,
                    "expected_market_delta": expected_market_delta,
                    "residual": residual,
                    "market_delta_5s": reversal_delta,
                },
            )

        return None
