"""TEMPLATE strategy configuration — copy and customize for new strategies.

Rename this module's class and replace the example fields with your strategy's
real parameters.  Keep ``get_default_config()`` returning an instance with
sensible production defaults.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S2Config(StrategyConfig):
    """Configuration for S2 Momentum strategy.
    
    Detect directional velocity between two time points and enter
    contrarian on strong momentum.
    """

    # Time window for velocity calculation
    eval_window_start: int = 30  # seconds (price_30s)
    eval_window_end: int = 60  # seconds (price_60s)
    
    # Minimum absolute velocity to trigger entry
    momentum_threshold: float = 0.03  # price change per second
    
    # Tolerance for NaN-aware price lookup
    tolerance: int = 10  # seconds


def get_default_config() -> S2Config:
    """Return the production-default S2 configuration.

    TODO: Update ``strategy_id`` to your folder name (e.g. ``'S3'``)
          and ``strategy_name`` to a descriptive slug (e.g. ``'S3_momentum'``).
    """
    return S2Config(
        strategy_id="S2",
        strategy_name="S2_momentum",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S2 Momentum strategy.

    Tests various evaluation windows, momentum thresholds, and tolerance
    to find optimal early momentum detection parameters.
    
    Total combinations: 3×3×4×2 = 72
    """
    return {
        "eval_window_start": [25, 30, 35],
        "eval_window_end": [55, 60, 65],
        "momentum_threshold": [0.02, 0.03, 0.05, 0.08],
        "tolerance": [5, 10],
    }
