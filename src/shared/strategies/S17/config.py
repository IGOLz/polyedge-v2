from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S17Config(StrategyConfig):
    """Configuration for S17 fair-value residual fade."""

    entry_window_start: int = 20
    entry_window_end: int = 180
    underlying_beta: float = 30.0
    residual_threshold: float = 0.04
    min_underlying_move_abs: float = 0.001
    reversal_confirmation_abs: float = 0.003
    extreme_price_low: float = 0.30
    extreme_price_high: float = 0.70


def get_default_config() -> S17Config:
    return S17Config(
        strategy_id="S17",
        strategy_name="S17_residual_fade",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [10, 20, 30, 45],
        "entry_window_end": [90, 120, 180, 240],
        "underlying_beta": [15.0, 20.0, 30.0, 40.0, 50.0],
        "residual_threshold": [0.02, 0.03, 0.04, 0.05],
        "min_underlying_move_abs": [0.0005, 0.001, 0.0015, 0.002],
        "reversal_confirmation_abs": [0.0, 0.002, 0.004, 0.006],
        "extreme_price_low": [0.20, 0.25, 0.30, 0.35],
        "extreme_price_high": [0.65, 0.70, 0.75, 0.80],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.60, 0.65, 0.70, 0.75],
    }
