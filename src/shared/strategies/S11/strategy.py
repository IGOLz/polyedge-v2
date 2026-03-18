"""S11 Strategy: midpoint reclaim."""

from __future__ import annotations

from shared.strategies.S11.config import S11Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price, valid_points


class S11Strategy(BaseStrategy):
    """Trade acceptance back through the midpoint after an earlier extreme."""

    config: S11Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config
        sec = current_second(snapshot)
        if sec < cfg.reclaim_scan_start or sec > cfg.reclaim_scan_end:
            return None

        hold_start = sec - cfg.hold_seconds + 1
        if hold_start <= 0:
            return None

        precondition_points = valid_points(
            prices,
            max(0, hold_start - cfg.precondition_window),
            hold_start - 1,
        )
        if len(precondition_points) < 4:
            return None

        had_downside_extreme = any(price <= 0.50 - cfg.extreme_deviation for _, price in precondition_points)
        had_upside_extreme = any(price >= 0.50 + cfg.extreme_deviation for _, price in precondition_points)

        hold_prices = []
        for hold_sec in range(hold_start, sec + 1):
            price = get_price(prices, hold_sec, tolerance=1)
            if price is None:
                return None
            hold_prices.append(price)

        confirm_price = hold_prices[-1]

        if had_downside_extreme and all(price >= 0.50 + cfg.hold_buffer for price in hold_prices):
            if confirm_price >= 0.50 + cfg.hold_buffer + cfg.post_reclaim_move:
                return Signal(
                    direction="Up",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, confirm_price)),
                    signal_data={
                        "entry_second": sec,
                        "observed_up_price": confirm_price,
                        "reclaim_side": "up",
                    },
                )

        if had_upside_extreme and all(price <= 0.50 - cfg.hold_buffer for price in hold_prices):
            if confirm_price <= 0.50 - cfg.hold_buffer - cfg.post_reclaim_move:
                return Signal(
                    direction="Down",
                    strategy_name=cfg.strategy_name,
                    entry_price=max(0.01, min(0.99, 1.0 - confirm_price)),
                    signal_data={
                        "entry_second": sec,
                        "observed_up_price": confirm_price,
                        "reclaim_side": "down",
                    },
                )

        return None
