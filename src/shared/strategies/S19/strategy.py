"""S19 Strategy: aggressor-flow confirmation."""

from __future__ import annotations

from shared.strategies.S19.config import S19Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_feature_value, get_price, get_window_feature_value


class S19Strategy(BaseStrategy):
    """Follow signals only when underlying taker flow agrees."""

    config: S19Config

    def required_feature_columns(self) -> tuple[str, ...]:
        return (
            f"underlying_return_{self.config.feature_window}s",
            f"market_up_delta_{self.config.feature_window}s",
            "underlying_volume",
            "underlying_taker_buy_base_volume",
            "underlying_trade_count",
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        underlying_return = get_window_feature_value(snapshot, "underlying_return", cfg.feature_window, sec)
        market_delta = get_window_feature_value(snapshot, "market_up_delta", cfg.feature_window, sec)
        total_volume = get_feature_value(snapshot, "underlying_volume", sec)
        taker_buy_volume = get_feature_value(snapshot, "underlying_taker_buy_base_volume", sec)
        trade_count = get_feature_value(snapshot, "underlying_trade_count", sec)
        if (
            up_price is None
            or underlying_return is None
            or market_delta is None
            or total_volume is None
            or taker_buy_volume is None
            or trade_count is None
        ):
            return None

        if total_volume <= 0.0 or total_volume < cfg.min_volume or trade_count < cfg.min_trade_count:
            return None
        if abs(up_price - 0.50) > cfg.max_price_distance_from_mid:
            return None

        imbalance = ((2.0 * taker_buy_volume) - total_volume) / total_volume

        if (
            imbalance >= cfg.buy_imbalance_threshold
            and underlying_return >= cfg.min_underlying_return
            and cfg.min_market_delta <= market_delta <= cfg.max_market_delta
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
                    "underlying_volume": total_volume,
                    "taker_buy_base_volume": taker_buy_volume,
                    "aggressor_imbalance": imbalance,
                    "trade_count": trade_count,
                },
            )

        if (
            imbalance <= -cfg.buy_imbalance_threshold
            and underlying_return <= -cfg.min_underlying_return
            and -cfg.max_market_delta <= market_delta <= -cfg.min_market_delta
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
                    "underlying_volume": total_volume,
                    "taker_buy_base_volume": taker_buy_volume,
                    "aggressor_imbalance": imbalance,
                    "trade_count": trade_count,
                },
            )

        return None
