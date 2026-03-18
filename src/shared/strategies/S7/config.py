from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S7Config(StrategyConfig):
    """Configuration for S7 ensemble confirmation."""

    min_agreement: int = 2
    calibration_enabled: bool = True
    momentum_enabled: bool = True
    volatility_enabled: bool = True

    calibration_entry_window_start: int = 30
    calibration_entry_window_end: int = 120
    calibration_price_low_threshold: float = 0.42
    calibration_price_high_threshold: float = 0.58
    calibration_min_deviation: float = 0.06
    calibration_rebound_lookback: int = 8
    calibration_rebound_min_move: float = 0.015

    momentum_eval_window_start: int = 30
    momentum_eval_window_end: int = 60
    momentum_threshold: float = 0.05
    momentum_tolerance: int = 3
    momentum_max_entry_second: int = 150
    momentum_efficiency_min: float = 0.65
    momentum_min_distance_from_mid: float = 0.04

    volatility_lookback_window: int = 60
    volatility_threshold: float = 0.025
    volatility_eval_second: int = 45
    volatility_extreme_price_low: float = 0.30
    volatility_extreme_price_high: float = 0.70
    volatility_reversal_lookback: int = 6
    volatility_reversal_min_move: float = 0.015


def get_default_config() -> S7Config:
    return S7Config(
        strategy_id="S7",
        strategy_name="S7_ensemble_confirmation",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "min_agreement": [2, 3],
        "calibration_enabled": [True, False],
        "momentum_enabled": [True, False],
        "volatility_enabled": [True, False],
        "calibration_min_deviation": [0.04, 0.06, 0.08],
        "calibration_rebound_min_move": [0.008, 0.012, 0.016],
        "momentum_threshold": [0.03, 0.05, 0.07],
        "momentum_efficiency_min": [0.55, 0.65, 0.75],
        "volatility_threshold": [0.018, 0.024, 0.03],
        "volatility_reversal_min_move": [0.008, 0.012, 0.016],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.65, 0.70, 0.75, 0.80],
    }
