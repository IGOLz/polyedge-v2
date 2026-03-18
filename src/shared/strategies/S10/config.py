"""S10 strategy configuration - pullback continuation."""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S10Config(StrategyConfig):
    """Configuration for S10 pullback continuation."""

    impulse_start: int = 20
    impulse_end: int = 60
    impulse_threshold: float = 0.08
    retrace_window: int = 30
    retrace_min: float = 0.10
    retrace_max: float = 0.45
    reacceleration_threshold: float = 0.02
    impulse_efficiency_min: float = 0.65


def get_default_config() -> S10Config:
    """Return the production-default S10 configuration."""
    return S10Config(
        strategy_id="S10",
        strategy_name="S10_pullback_continuation",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S10.

    Total combinations: 921,600
    """
    return {
        "impulse_start": [10, 20, 30, 45],
        "impulse_end": [45, 60, 75, 90],
        "impulse_threshold": [0.05, 0.075, 0.10, 0.125],
        "retrace_window": [10, 20, 30, 45],
        "retrace_min": [0.10, 0.15, 0.20],
        "retrace_max": [0.35, 0.45, 0.55, 0.65],
        "reacceleration_threshold": [0.01, 0.02, 0.03, 0.04],
        "impulse_efficiency_min": [0.55, 0.65, 0.75],
        "stop_loss": [0.25, 0.30, 0.35, 0.40, 0.45],
        "take_profit": [0.60, 0.65, 0.70, 0.75, 0.80],
    }
