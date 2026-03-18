from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S1Config(StrategyConfig):
    """Configuration for S1 balanced-mispricing fade."""

    entry_window_start: int = 30
    entry_window_end: int = 120
    price_low_threshold: float = 0.42
    price_high_threshold: float = 0.58
    min_deviation: float = 0.06
    rebound_lookback: int = 8
    rebound_min_move: float = 0.015


def get_default_config() -> S1Config:
    return S1Config(
        strategy_id="S1",
        strategy_name="S1_balanced_mispricing_fade",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [20, 30, 45, 60],
        "entry_window_end": [75, 105, 135, 180],
        "price_low_threshold": [0.38, 0.40, 0.42, 0.45],
        "price_high_threshold": [0.55, 0.58, 0.60, 0.62],
        "min_deviation": [0.04, 0.06, 0.08, 0.10],
        "rebound_lookback": [4, 6, 8, 12],
        "rebound_min_move": [0.008, 0.012, 0.016, 0.02],
        "stop_loss": [0.25, 0.30, 0.35, 0.40],
        "take_profit": [0.60, 0.65, 0.70, 0.75],
    }
