"""S18 Strategy: multi-window acceleration follow."""

from __future__ import annotations

from shared.strategies.S18.config import S18Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_feature_value, get_price, get_window_feature_value


class S18Strategy(BaseStrategy):
    """Follow underlying acceleration when Polymarket is aligned but not exhausted."""

    config: S18Config

    def required_feature_columns(self) -> tuple[str, ...]:
        return (
            "underlying_return_5s",
            "underlying_return_10s",
            "underlying_return_30s",
            "underlying_realized_vol_30s",
            "underlying_trade_count",
            "market_up_delta_5s",
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.entry_window_start or sec > cfg.entry_window_end:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=1)
        ret_5s = get_window_feature_value(snapshot, "underlying_return", 5, sec)
        ret_10s = get_window_feature_value(snapshot, "underlying_return", 10, sec)
        ret_30s = get_window_feature_value(snapshot, "underlying_return", 30, sec)
        underlying_vol = get_window_feature_value(snapshot, "underlying_realized_vol", 30, sec)
        trade_count = get_feature_value(snapshot, "underlying_trade_count", sec)
        market_delta_5s = get_window_feature_value(snapshot, "market_up_delta", 5, sec)
        if (
            up_price is None
            or ret_5s is None
            or ret_10s is None
            or ret_30s is None
            or underlying_vol is None
            or trade_count is None
            or market_delta_5s is None
        ):
            return None

        if underlying_vol > cfg.max_underlying_vol or trade_count < cfg.min_trade_count:
            return None
        if abs(up_price - 0.50) > cfg.max_price_distance_from_mid:
            return None

        if (
            ret_30s >= cfg.min_return_30s
            and ret_10s >= cfg.min_return_10s
            and ret_5s >= cfg.min_return_5s
            and ret_5s >= abs(ret_10s) * cfg.acceleration_ratio
            and market_delta_5s >= 0.0
            and up_price > 0.50
        ):
            return Signal(
                direction="Up",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "underlying_return_5s": ret_5s,
                    "underlying_return_10s": ret_10s,
                    "underlying_return_30s": ret_30s,
                    "underlying_vol_30s": underlying_vol,
                    "market_delta_5s": market_delta_5s,
                    "trade_count": trade_count,
                },
            )

        if (
            ret_30s <= -cfg.min_return_30s
            and ret_10s <= -cfg.min_return_10s
            and ret_5s <= -cfg.min_return_5s
            and abs(ret_5s) >= abs(ret_10s) * cfg.acceleration_ratio
            and market_delta_5s <= 0.0
            and up_price < 0.50
        ):
            return Signal(
                direction="Down",
                strategy_name=cfg.strategy_name,
                entry_price=max(0.01, min(0.99, 1.0 - up_price)),
                signal_data={
                    "entry_second": sec,
                    "observed_up_price": up_price,
                    "underlying_return_5s": ret_5s,
                    "underlying_return_10s": ret_10s,
                    "underlying_return_30s": ret_30s,
                    "underlying_vol_30s": underlying_vol,
                    "market_delta_5s": market_delta_5s,
                    "trade_count": trade_count,
                },
            )

        return None
