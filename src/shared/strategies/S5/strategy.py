"""S5 Strategy: time-phase midpoint reclaim."""

from __future__ import annotations

from shared.strategies.S5.config import S5Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price, trailing_net_move


class S5Strategy(BaseStrategy):
    """Trade midpoint crosses only during the time phases you trust."""

    config: S5Config

    def market_is_eligible(self, market: dict) -> bool:
        if not super().market_is_eligible(market):
            return False

        cfg = self.config
        asset = str(market.get("asset", "")).lower()
        duration_minutes = int(market.get("duration_minutes", 0) or 0)
        hour = market.get("hour")

        if cfg.allowed_assets is not None:
            allowed_assets = {value.lower() for value in cfg.allowed_assets}
            if asset not in allowed_assets:
                return False

        if cfg.allowed_durations_minutes is not None:
            if duration_minutes not in cfg.allowed_durations_minutes:
                return False

        if cfg.allowed_hours is not None and hour is not None:
            if hour not in cfg.allowed_hours:
                return False

        return True

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        asset = str(snapshot.metadata.get("asset", "")).lower()
        duration_minutes = int(snapshot.metadata.get("duration_minutes", 0) or 0)
        current_hour = snapshot.metadata.get("hour")

        if cfg.allowed_assets is not None:
            allowed_assets = {value.lower() for value in cfg.allowed_assets}
            if asset not in allowed_assets:
                return None

        if cfg.allowed_durations_minutes is not None:
            if duration_minutes not in cfg.allowed_durations_minutes:
                return None

        if cfg.allowed_hours is not None:
            if not cfg.allowed_hours:
                return None
            if current_hour is not None and current_hour not in cfg.allowed_hours:
                return None

        price = get_price(prices, sec, tolerance=2)
        prev_price = get_price(prices, sec - cfg.approach_lookback, tolerance=2)
        if price is None or prev_price is None:
            return None

        if not (cfg.price_range_low <= price <= cfg.price_range_high):
            return None

        recent_move = trailing_net_move(prices, sec, cfg.confirmation_lookback)
        if recent_move is None:
            return None

        cross_move = price - prev_price

        if (
            prev_price <= 0.50 - cfg.cross_buffer
            and price >= 0.50 + cfg.cross_buffer
            and cross_move >= cfg.min_cross_move
            and recent_move >= cfg.confirmation_min_move
        ):
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": price,
                    "previous_up_price": prev_price,
                    "hour": current_hour,
                    "recent_move": recent_move,
                    "cross_move": cross_move,
                    "stop_loss_price": cfg.live_stop_loss_price,
                    "take_profit_price": cfg.live_take_profit_price,
                },
            )

        if (
            prev_price >= 0.50 + cfg.cross_buffer
            and price <= 0.50 - cfg.cross_buffer
            and cross_move <= -cfg.min_cross_move
            and recent_move <= -cfg.confirmation_min_move
        ):
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": price,
                    "previous_up_price": prev_price,
                    "hour": current_hour,
                    "recent_move": recent_move,
                    "cross_move": cross_move,
                    "stop_loss_price": cfg.live_stop_loss_price,
                    "take_profit_price": cfg.live_take_profit_price,
                },
            )

        return None
