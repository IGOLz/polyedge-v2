"""S13 Strategy: underlying lag follow."""

from __future__ import annotations

from shared.strategies.S13.config import S13Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import (
    current_second,
    get_price,
    get_window_feature_value,
)


class S13Strategy(BaseStrategy):
    """Follow the underlying when Polymarket looks late, not finished."""

    config: S13Config

    def market_is_eligible(self, market: dict) -> bool:
        if not super().market_is_eligible(market):
            return False

        allowed_assets = self.config.allowed_assets
        if allowed_assets is not None:
            asset = str(market.get("asset", "")).lower()
            if asset not in {value.lower() for value in allowed_assets}:
                return False

        allowed_durations = self.config.allowed_durations_minutes
        if allowed_durations is not None:
            duration_minutes = int(market.get("duration_minutes", 0) or 0)
            if duration_minutes not in allowed_durations:
                return False

        return True

    def required_feature_columns(self) -> tuple[str, ...]:
        vol_window = 10 if self.config.feature_window == 5 else 30
        return (
            f"underlying_return_{self.config.feature_window}s",
            f"market_up_delta_{self.config.feature_window}s",
            f"underlying_realized_vol_{vol_window}s",
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        if cfg.allowed_assets is not None:
            asset = str(snapshot.metadata.get("asset", "")).lower()
            if asset not in {value.lower() for value in cfg.allowed_assets}:
                return None

        if cfg.allowed_durations_minutes is not None:
            duration_minutes = int(snapshot.metadata.get("duration_minutes", 0) or 0)
            if duration_minutes not in cfg.allowed_durations_minutes:
                return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        underlying_return = get_window_feature_value(snapshot, "underlying_return", cfg.feature_window, sec)
        market_delta = get_window_feature_value(snapshot, "market_up_delta", cfg.feature_window, sec)
        vol_window = 10 if cfg.feature_window == 5 else 30
        underlying_vol = get_window_feature_value(snapshot, "underlying_realized_vol", vol_window, sec)
        if up_price is None or underlying_return is None or market_delta is None or underlying_vol is None:
            return None
        if underlying_vol > cfg.max_underlying_vol:
            return None

        price_distance = abs(up_price - 0.50)
        if price_distance > cfg.max_price_distance_from_mid:
            return None

        if (
            underlying_return >= cfg.min_underlying_return
            and cfg.min_market_confirmation <= market_delta <= cfg.max_market_delta
            and up_price > 0.50
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
                    "underlying_vol": underlying_vol,
                    "stop_loss_price": cfg.live_stop_loss_price,
                    "take_profit_price": cfg.live_take_profit_price,
                },
            )

        if (
            underlying_return <= -cfg.min_underlying_return
            and -cfg.max_market_delta <= market_delta <= -cfg.min_market_confirmation
            and up_price < 0.50
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
                    "underlying_vol": underlying_vol,
                    "stop_loss_price": cfg.live_stop_loss_price,
                    "take_profit_price": cfg.live_take_profit_price,
                },
            )

        return None
