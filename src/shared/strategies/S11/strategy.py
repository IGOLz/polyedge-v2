"""S11 Strategy: midpoint reclaim."""

from __future__ import annotations

from shared.strategies.S11.config import S11Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import get_price, valid_points


class S11Strategy(BaseStrategy):
    """Trade acceptance back through the midpoint after an earlier extreme."""

    config: S11Config

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        prices = snapshot.prices
        cfg = self.config

        scan_end = min(cfg.reclaim_scan_end, len(prices) - 1)
        if cfg.reclaim_scan_start >= scan_end:
            return None

        for sec in range(cfg.reclaim_scan_start, scan_end + 1):
            confirm_end = sec + cfg.hold_seconds - 1
            if confirm_end >= len(prices):
                break

            precondition_points = valid_points(
                prices,
                max(0, sec - cfg.precondition_window),
                sec - 1,
            )
            if len(precondition_points) < 4:
                continue

            had_downside_extreme = any(
                price <= 0.50 - cfg.extreme_deviation
                for _, price in precondition_points
            )
            had_upside_extreme = any(
                price >= 0.50 + cfg.extreme_deviation
                for _, price in precondition_points
            )

            hold_prices: list[float] = []
            for hold_sec in range(sec, confirm_end + 1):
                price = get_price(prices, hold_sec, tolerance=1)
                if price is None:
                    hold_prices = []
                    break
                hold_prices.append(price)

            if len(hold_prices) != cfg.hold_seconds:
                continue

            confirm_price = hold_prices[-1]

            if had_downside_extreme and all(
                price >= 0.50 + cfg.hold_buffer
                for price in hold_prices
            ):
                if confirm_price >= 0.50 + cfg.hold_buffer + cfg.post_reclaim_move:
                    return Signal(
                        direction="Up",
                        strategy_name=cfg.strategy_name,
                        entry_price=max(0.01, min(0.99, confirm_price)),
                        signal_data={
                            "entry_second": confirm_end,
                            "reclaim_start": sec,
                            "reclaim_side": "up",
                        },
                    )

            if had_upside_extreme and all(
                price <= 0.50 - cfg.hold_buffer
                for price in hold_prices
            ):
                if confirm_price <= 0.50 - cfg.hold_buffer - cfg.post_reclaim_move:
                    return Signal(
                        direction="Down",
                        strategy_name=cfg.strategy_name,
                        entry_price=max(0.01, min(0.99, 1.0 - confirm_price)),
                        signal_data={
                            "entry_second": confirm_end,
                            "reclaim_start": sec,
                            "reclaim_side": "down",
                        },
                    )

        return None
