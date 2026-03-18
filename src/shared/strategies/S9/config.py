"""S9 strategy configuration - compression breakout continuation."""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S9Config(StrategyConfig):
    """Configuration for S9 compression breakout continuation."""

    compression_window: int = 45
    compression_max_std: float = 0.015
    compression_max_range: float = 0.04
    trigger_scan_start: int = 50
    trigger_scan_end: int = 150
    breakout_distance: float = 0.03
    momentum_lookback: int = 10
    efficiency_min: float = 0.65


def get_default_config() -> S9Config:
    """Return the production-default S9 configuration."""
    return S9Config(
        strategy_id="S9",
        strategy_name="S9_compression_breakout",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S9.

    Total combinations: 786,432
    """
    return {
        "compression_window": [20, 30, 45, 60],
        "compression_max_std": [0.008, 0.012, 0.016, 0.02],
        "compression_max_range": [0.03, 0.04, 0.05, 0.06],
        "trigger_scan_start": [30, 45, 60, 75],
        "trigger_scan_end": [90, 120, 150, 180],
        "breakout_distance": [0.02, 0.03, 0.04, 0.05],
        "momentum_lookback": [5, 10, 15],
        "efficiency_min": [0.55, 0.65, 0.75, 0.85],
        "stop_loss": [0.25, 0.30, 0.35, 0.40],
        "take_profit": [0.60, 0.65, 0.70, 0.75],
    }
