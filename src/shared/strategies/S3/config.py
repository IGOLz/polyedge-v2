"""TEMPLATE strategy configuration — copy and customize for new strategies.

Rename this module's class and replace the example fields with your strategy's
real parameters.  Keep ``get_default_config()`` returning an instance with
sensible production defaults.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S3Config(StrategyConfig):
    """Configuration for S3 Mean Reversion strategy.
    
    Detect early price spikes, wait for partial reversion,
    then enter contrarian bet on continued reversion to balanced price.
    """

    # Spike detection parameters
    spike_threshold: float = 0.75  # price threshold for spike detection
    spike_lookback: int = 30  # seconds to scan for spike
    
    # Reversion detection parameters
    reversion_pct: float = 0.10  # fraction of peak-to-balanced to revert
    min_reversion_sec: int = 60  # seconds after peak to scan for reversion


def get_default_config() -> S3Config:
    """Return the production-default S3 configuration.

    TODO: Update ``strategy_id`` to your folder name (e.g. ``'S3'``)
          and ``strategy_name`` to a descriptive slug (e.g. ``'S3_momentum'``).
    """
    return S3Config(
        strategy_id="S3",
        strategy_name="S3_reversion",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S3 Mean Reversion strategy.

    Tests various spike thresholds, lookback windows, reversion percentages,
    and minimum reversion seconds to find optimal mean reversion parameters.
    
    Total combinations: 4×3×4×3 = 144
    """
    return {
        "spike_threshold": [0.70, 0.75, 0.80, 0.85],
        "spike_lookback": [15, 30, 60],
        "reversion_pct": [0.05, 0.08, 0.10, 0.15],
        "min_reversion_sec": [30, 60, 120],
    }
