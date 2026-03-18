"""S1 (Spike Reversion) strategy configuration.

Parameter values sourced from trading/constants.py M3_CONFIG.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S1Config(StrategyConfig):
    """Configuration for the spike-reversion strategy."""

    # Spike detection
    spike_detection_window_seconds: int = 15
    spike_threshold_up: float = 0.80
    spike_threshold_down: float = 0.20

    # Reversion detection
    reversion_reversal_pct: float = 0.10
    min_reversion_ticks: int = 10

    # Entry
    entry_price_threshold: float = 0.35


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S1.

    Covers three key tunable parameters with 3 values each (27 combinations).
    """
    return {
        "spike_threshold_up": [0.75, 0.80, 0.85],
        "reversion_reversal_pct": [0.08, 0.10, 0.12],
        "entry_price_threshold": [0.30, 0.35, 0.40],
    }


def get_default_config() -> S1Config:
    """Return the production-default S1 configuration."""
    return S1Config(
        strategy_id="S1",
        strategy_name="S1_spike_reversion",
    )
