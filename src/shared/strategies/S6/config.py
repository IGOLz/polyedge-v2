"""S6 strategy configuration — Streak/Sequence detection parameters.

Detects consecutive same-direction price moves within a single market
and enters contrarian when streak length reaches threshold.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S6Config(StrategyConfig):
    """Configuration for S6 Streak/Sequence strategy.

    Detects consecutive same-direction price moves within a single market
    and enters contrarian when streak length reaches threshold.
    """

    # Size of each time window in seconds
    window_size: int = 15

    # Number of consecutive same-direction windows to trigger entry
    streak_length: int = 3

    # Minimum price move to classify window direction (not flat)
    min_move_threshold: float = 0.03

    # Minimum number of windows required before evaluating
    min_windows: int = 5


def get_default_config() -> S6Config:
    """Return the production-default S6 configuration."""
    return S6Config(
        strategy_id="S6",
        strategy_name="S6_streak",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for this strategy.

    The optimizer generates the Cartesian product of all parameter values
    and backtests every combination.

    Returns:
        4 × 3 × 3 × 2 = 72 parameter combinations
    """
    return {
        "window_size": [10, 15, 20, 30],
        "streak_length": [3, 4, 5],
        "min_move_threshold": [0.02, 0.03, 0.05],
        "min_windows": [4, 5],
    }
