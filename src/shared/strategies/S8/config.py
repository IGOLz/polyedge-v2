"""S8 strategy configuration - opening range breakout continuation."""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S8Config(StrategyConfig):
    """Configuration for S8 opening range breakout continuation."""

    setup_window_end: int = 45
    breakout_scan_start: int = 50
    breakout_scan_end: int = 150
    breakout_buffer: float = 0.02
    min_range_width: float = 0.03
    max_range_width: float = 0.18
    confirmation_points: int = 2
    min_distance_from_mid: float = 0.04


def get_default_config() -> S8Config:
    """Return the production-default S8 configuration."""
    return S8Config(
        strategy_id="S8",
        strategy_name="S8_opening_range_breakout",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S8.

    Total combinations: 192,000
    """
    return {
        "setup_window_end": [20, 30, 45, 60],
        "breakout_scan_start": [25, 40, 55, 70],
        "breakout_scan_end": [90, 120, 150, 180, 240],
        "breakout_buffer": [0.01, 0.015, 0.02, 0.03, 0.04],
        "min_range_width": [0.02, 0.03, 0.04, 0.05],
        "max_range_width": [0.10, 0.15, 0.20, 0.25],
        "confirmation_points": [1, 2, 3, 4],
        "min_distance_from_mid": [0.02, 0.04, 0.06],
        "stop_loss": [0.25, 0.30, 0.35, 0.40, 0.45],
        "take_profit": [0.55, 0.60, 0.65, 0.70, 0.75],
    }
