"""S2 (Volatility) strategy configuration.

Parameter values sourced from trading/constants.py M4_CONFIG.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S2Config(StrategyConfig):
    """Configuration for the volatility strategy."""

    # Evaluation timing
    eval_second: int = 30
    eval_window: int = 2

    # Volatility detection
    volatility_window_seconds: int = 10
    volatility_threshold: float = 0.05

    # Spread filter
    min_spread: float = 0.05
    max_spread: float = 0.50

    # Base deviation filter
    base_deviation: float = 0.08


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S2.

    Covers three key tunable parameters with 3 values each (27 combinations).
    """
    return {
        "volatility_threshold": [0.03, 0.05, 0.07],
        "min_spread": [0.03, 0.05, 0.07],
        "base_deviation": [0.06, 0.08, 0.10],
    }


def get_default_config() -> S2Config:
    """Return the production-default S2 configuration."""
    return S2Config(
        strategy_id="S2",
        strategy_name="S2_volatility",
    )
