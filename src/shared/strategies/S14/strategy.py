"""S14 Strategy: divergence fade."""

from __future__ import annotations

from shared.strategies.S14.config import S14Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_feature_value, get_price, get_window_feature_value


class S14Strategy(BaseStrategy):
    """Fade Polymarket moves that the underlying does not confirm."""

    config: S14Config

    def market_is_eligible(self, market: dict) -> bool:
        if not super().market_is_eligible(market):
            return False

        allowed_durations = self.config.allowed_durations_minutes
        if allowed_durations is not None:
            duration_minutes = int(market.get("duration_minutes", 0) or 0)
            if duration_minutes not in allowed_durations:
                return False

        return True

    def required_feature_columns(self) -> tuple[str, ...]:
        columns = [
            f"underlying_return_{self.config.feature_window}s",
            f"market_up_delta_{self.config.feature_window}s",
        ]
        if self.config.require_direction_mismatch:
            columns.append(f"direction_mismatch_{self.config.feature_window}s")
        return tuple(columns)

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        if cfg.allowed_durations_minutes is not None:
            duration_minutes = int(snapshot.metadata.get("duration_minutes", 0) or 0)
            if duration_minutes not in cfg.allowed_durations_minutes:
                return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        underlying_return = get_window_feature_value(snapshot, "underlying_return", cfg.feature_window, sec)
        market_delta = get_window_feature_value(snapshot, "market_up_delta", cfg.feature_window, sec)
        mismatch = get_feature_value(snapshot, f"direction_mismatch_{cfg.feature_window}s", sec)
        if up_price is None or underlying_return is None or market_delta is None:
            return None

        mismatch_ok = True
        if cfg.require_direction_mismatch:
            mismatch_ok = mismatch is not None and mismatch >= 0.5

        if (
            market_delta >= cfg.min_market_delta_abs
            and abs(underlying_return) <= cfg.max_underlying_return_abs
            and up_price >= cfg.extreme_price_high
            and mismatch_ok
        ):
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "underlying_return": underlying_return,
                    "market_delta": market_delta,
                    "direction_mismatch": mismatch,
                    "stop_loss_price": cfg.live_stop_loss_price,
                    "take_profit_price": cfg.live_take_profit_price,
                },
            )

        if (
            market_delta <= -cfg.min_market_delta_abs
            and abs(underlying_return) <= cfg.max_underlying_return_abs
            and up_price <= cfg.extreme_price_low
            and mismatch_ok
        ):
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "underlying_return": underlying_return,
                    "market_delta": market_delta,
                    "direction_mismatch": mismatch,
                    "stop_loss_price": cfg.live_stop_loss_price,
                    "take_profit_price": cfg.live_take_profit_price,
                },
            )

        return None
