"""S7 Strategy: ensemble confirmation."""

from __future__ import annotations

from shared.strategies.S1.config import S1Config
from shared.strategies.S1.strategy import S1Strategy
from shared.strategies.S2.config import S2Config
from shared.strategies.S2.strategy import S2Strategy
from shared.strategies.S4.config import S4Config
from shared.strategies.S4.strategy import S4Strategy
from shared.strategies.S7.config import S7Config
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.helpers import current_second, get_price


class S7Strategy(BaseStrategy):
    """Require multiple updated causal detectors to agree right now."""

    config: S7Config

    def _build_calibration_strategy(self) -> S1Strategy:
        cfg = self.config
        return S1Strategy(
            S1Config(
                strategy_id="S1",
                strategy_name="S7_calibration_component",
                entry_window_start=cfg.calibration_entry_window_start,
                entry_window_end=cfg.calibration_entry_window_end,
                price_low_threshold=cfg.calibration_price_low_threshold,
                price_high_threshold=cfg.calibration_price_high_threshold,
                min_deviation=cfg.calibration_min_deviation,
                rebound_lookback=cfg.calibration_rebound_lookback,
                rebound_min_move=cfg.calibration_rebound_min_move,
            )
        )

    def _build_momentum_strategy(self) -> S2Strategy:
        cfg = self.config
        return S2Strategy(
            S2Config(
                strategy_id="S2",
                strategy_name="S7_momentum_component",
                eval_window_start=cfg.momentum_eval_window_start,
                eval_window_end=cfg.momentum_eval_window_end,
                momentum_threshold=cfg.momentum_threshold,
                tolerance=cfg.momentum_tolerance,
                max_entry_second=cfg.momentum_max_entry_second,
                efficiency_min=cfg.momentum_efficiency_min,
                min_distance_from_mid=cfg.momentum_min_distance_from_mid,
            )
        )

    def _build_volatility_strategy(self) -> S4Strategy:
        cfg = self.config
        return S4Strategy(
            S4Config(
                strategy_id="S4",
                strategy_name="S7_volatility_component",
                lookback_window=cfg.volatility_lookback_window,
                vol_threshold=cfg.volatility_threshold,
                eval_second=cfg.volatility_eval_second,
                extreme_price_low=cfg.volatility_extreme_price_low,
                extreme_price_high=cfg.volatility_extreme_price_high,
                reversal_lookback=cfg.volatility_reversal_lookback,
                reversal_min_move=cfg.volatility_reversal_min_move,
            )
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        cfg = self.config
        sec = current_second(snapshot)
        detections = []

        if cfg.calibration_enabled:
            signal = self._build_calibration_strategy().evaluate(snapshot)
            if signal is not None:
                detections.append(signal.direction)

        if cfg.momentum_enabled:
            signal = self._build_momentum_strategy().evaluate(snapshot)
            if signal is not None:
                detections.append(signal.direction)

        if cfg.volatility_enabled:
            signal = self._build_volatility_strategy().evaluate(snapshot)
            if signal is not None:
                detections.append(signal.direction)

        up_votes = sum(1 for direction in detections if direction == "Up")
        down_votes = sum(1 for direction in detections if direction == "Down")

        if up_votes >= cfg.min_agreement:
            direction = "Up"
        elif down_votes >= cfg.min_agreement:
            direction = "Down"
        else:
            return None

        up_price = get_price(snapshot.prices, sec, tolerance=2)
        if up_price is None:
            return None

        entry_price = up_price if direction == "Up" else 1.0 - up_price
        return Signal(
            direction=direction,
            strategy_name=cfg.strategy_name,
            entry_price=max(0.01, min(0.99, entry_price)),
            signal_data={
                "entry_second": sec,
                "observed_up_price": up_price,
                "up_votes": up_votes,
                "down_votes": down_votes,
                "detections": len(detections),
            },
        )
