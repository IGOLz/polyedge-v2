"""S12 strategy configuration - late trend confirmation."""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S12Config(StrategyConfig):
    """Configuration for S12 late trend confirmation."""

    late_phase_start_pct: float = 0.65
    lookback_seconds: int = 30
    net_move_threshold: float = 0.06
    efficiency_min: float = 0.65
    max_flip_count: int = 1
    min_price_distance_from_mid: float = 0.05
    min_remaining_seconds: int = 30


def get_default_config() -> S12Config:
    """Return the production-default S12 configuration."""
    return S12Config(
        strategy_id="S12",
        strategy_name="S12_late_trend_confirmation",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S12.

    Total combinations: 262,144
    """
    return {
        "late_phase_start_pct": [0.55, 0.65, 0.75, 0.85],
        "lookback_seconds": [20, 30, 45, 60],
        "net_move_threshold": [0.04, 0.06, 0.08, 0.10],
        "efficiency_min": [0.55, 0.65, 0.75, 0.85],
        "max_flip_count": [0, 1, 2, 3],
        "min_price_distance_from_mid": [0.03, 0.05, 0.07, 0.10],
        "min_remaining_seconds": [15, 30, 45, 60],
        "stop_loss": [0.30, 0.35, 0.40, 0.45],
        "take_profit": [0.60, 0.65, 0.70, 0.75],
    }
