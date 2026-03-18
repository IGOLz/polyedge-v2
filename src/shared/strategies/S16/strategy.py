"""S16 Strategy: underlying reversal catch-up."""

from __future__ import annotations

from shared.strategies.S16.config import S16Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price, get_window_feature_value


class S16Strategy(BaseStrategy):
    """Catch sharp underlying reversals when Polymarket still sits on the old side."""

    config: S16Config

    def required_feature_columns(self) -> tuple[str, ...]:
        vol_window = 10 if self.config.short_window == 5 else 30
        return (
            f"underlying_return_{self.config.short_window}s",
            f"underlying_return_{self.config.long_window}s",
            f"underlying_realized_vol_{vol_window}s",
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        if cfg.short_window not in {5, 10}:
            return None
        if cfg.long_window not in {10, 30}:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        short_return = get_window_feature_value(snapshot, "underlying_return", cfg.short_window, sec)
        long_return = get_window_feature_value(snapshot, "underlying_return", cfg.long_window, sec)
        vol_window = 10 if cfg.short_window == 5 else 30
        underlying_vol = get_window_feature_value(snapshot, "underlying_realized_vol", vol_window, sec)
        if up_price is None or short_return is None or long_return is None or underlying_vol is None:
            return None
        if underlying_vol > cfg.max_underlying_vol:
            return None

        if (
            short_return >= cfg.min_short_return
            and long_return <= -cfg.min_long_return_opposite
            and up_price <= 0.50 - cfg.min_price_distance_from_mid
        ):
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "short_return": short_return,
                    "long_return": long_return,
                    "underlying_vol": underlying_vol,
                },
            )

        if (
            short_return <= -cfg.min_short_return
            and long_return >= cfg.min_long_return_opposite
            and up_price >= 0.50 + cfg.min_price_distance_from_mid
        ):
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "short_return": short_return,
                    "long_return": long_return,
                    "underlying_vol": underlying_vol,
                },
            )

        return None
