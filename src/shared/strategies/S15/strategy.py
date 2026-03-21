"""S15 Strategy: breakout with underlying confirmation."""

from __future__ import annotations

import numpy as np

from shared.strategies.S15.config import S15Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import (
    current_second,
    get_feature_value,
    get_price,
    get_window_feature_value,
    valid_points,
)


class S15Strategy(BaseStrategy):
    """Only take breakouts when the underlying is moving the same way."""

    config: S15Config

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
        return (
            f"underlying_return_{self.config.feature_window}s",
            "underlying_trade_count",
        )

    def _confirmed(self, prices: np.ndarray, sec: int, threshold: float, is_up: bool) -> bool:
        for check_sec in range(sec - self.config.confirmation_points + 1, sec + 1):
            price = get_price(prices, check_sec, tolerance=1)
            if price is None:
                return False
            if is_up and price < threshold:
                return False
            if not is_up and price > threshold:
                return False
        return True

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < max(cfg.breakout_scan_start, cfg.setup_window_end + 1):
            return None
        if sec > cfg.breakout_scan_end:
            return None

        if cfg.allowed_assets is not None:
            asset = str(snapshot.metadata.get("asset", "")).lower()
            if asset not in {value.lower() for value in cfg.allowed_assets}:
                return None

        if cfg.allowed_durations_minutes is not None:
            duration_minutes = int(snapshot.metadata.get("duration_minutes", 0) or 0)
            if duration_minutes not in cfg.allowed_durations_minutes:
                return None

        setup_points = valid_points(snapshot.prices, 0, min(cfg.setup_window_end, sec - 1))
        if len(setup_points) < 6:
            return None

        setup_values = np.array([price for _, price in setup_points], dtype=float)
        range_high = float(np.max(setup_values))
        range_low = float(np.min(setup_values))
        up_price = get_price(snapshot.prices, sec, tolerance=1)
        underlying_return = get_window_feature_value(snapshot, "underlying_return", cfg.feature_window, sec)
        trade_count = get_feature_value(snapshot, "underlying_trade_count", sec)
        if up_price is None or underlying_return is None or trade_count is None:
            return None
        if trade_count < cfg.min_trade_count:
            return None

        up_threshold = range_high + cfg.breakout_buffer
        down_threshold = range_low - cfg.breakout_buffer

        if (
            up_price >= up_threshold
            and underlying_return >= cfg.min_underlying_return
            and self._confirmed(snapshot.prices, sec, up_threshold, True)
        ):
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "underlying_return": underlying_return,
                    "trade_count": trade_count,
                    "stop_loss_price": cfg.live_stop_loss_price,
                    "take_profit_price": cfg.live_take_profit_price,
                },
            )

        if (
            up_price <= down_threshold
            and underlying_return <= -cfg.min_underlying_return
            and self._confirmed(snapshot.prices, sec, down_threshold, False)
        ):
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "underlying_return": underlying_return,
                    "trade_count": trade_count,
                    "stop_loss_price": cfg.live_stop_loss_price,
                    "take_profit_price": cfg.live_take_profit_price,
                },
            )

        return None
