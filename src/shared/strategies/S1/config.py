from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S1Config(StrategyConfig):
    """Configuration for S1 balanced-mispricing fade."""

    entry_window_start: int = 20
    entry_window_end: int = 105
    price_low_threshold: float = 0.40
    price_high_threshold: float = 0.58
    min_deviation: float = 0.08
    rebound_lookback: int = 12
    rebound_min_move: float = 0.008


def get_default_config() -> S1Config:
    return S1Config(
        strategy_id="S1",
        strategy_name="S1_balanced_mispricing_fade",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [15, 20, 25],
        "entry_window_end": [90, 105, 120],
        "price_low_threshold": [0.39, 0.40, 0.41],
        "price_high_threshold": [0.55, 0.57, 0.59, 0.60],
        "min_deviation": [0.07, 0.08, 0.09],
        "rebound_lookback": [10, 12, 14],
        "rebound_min_move": [0.006, 0.008, 0.010, 0.012],
        "stop_loss": [0.28, 0.30, 0.32],
        "take_profit": [0.70, 0.75, 0.80],
    }
