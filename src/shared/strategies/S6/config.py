from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S6Config(StrategyConfig):
    """Configuration for S6 prior-market streak fade."""

    streak_length: int = 3
    streak_direction_filter: str = "both"  # 'Up', 'Down', or 'both'
    entry_window_start: int = 0
    entry_window_end: int = 30
    price_floor: float = 0.20
    price_ceiling: float = 0.80


def get_default_config() -> S6Config:
    return S6Config(
        strategy_id="S6",
        strategy_name="S6_prior_market_streak_fade",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "streak_length": [2, 3, 4, 5, 6],
        "streak_direction_filter": ["Up", "Down", "both"],
        "entry_window_start": [0, 5, 10, 15],
        "entry_window_end": [15, 30, 45, 60],
        "price_floor": [0.15, 0.20, 0.25, 0.30],
        "price_ceiling": [0.70, 0.75, 0.80, 0.85],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.60, 0.65, 0.70, 0.75],
    }
