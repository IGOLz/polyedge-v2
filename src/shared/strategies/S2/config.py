from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S2Config(StrategyConfig):
    """Configuration for S2 early momentum continuation."""

    eval_window_start: int = 30
    eval_window_end: int = 60
    momentum_threshold: float = 0.05
    tolerance: int = 3
    max_entry_second: int = 150
    efficiency_min: float = 0.65
    min_distance_from_mid: float = 0.04


def get_default_config() -> S2Config:
    return S2Config(
        strategy_id="S2",
        strategy_name="S2_early_momentum_continuation",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "eval_window_start": [10, 20, 30, 45],
        "eval_window_end": [30, 45, 60, 75],
        "momentum_threshold": [0.03, 0.05, 0.07, 0.09],
        "tolerance": [2, 3, 5],
        "max_entry_second": [90, 120, 150, 180],
        "efficiency_min": [0.55, 0.65, 0.75, 0.85],
        "min_distance_from_mid": [0.02, 0.04, 0.06, 0.08],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.65, 0.70, 0.75, 0.80],
    }
