"""S11 strategy configuration - midpoint reclaim."""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S11Config(StrategyConfig):
    """Configuration for S11 midpoint reclaim."""

    precondition_window: int = 45
    extreme_deviation: float = 0.10
    reclaim_scan_start: int = 35
    reclaim_scan_end: int = 150
    hold_seconds: int = 4
    hold_buffer: float = 0.01
    post_reclaim_move: float = 0.02


def get_default_config() -> S11Config:
    """Return the production-default S11 configuration."""
    return S11Config(
        strategy_id="S11",
        strategy_name="S11_midpoint_reclaim",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S11.

    Total combinations: 307,200
    """
    return {
        "precondition_window": [15, 30, 45, 60],
        "extreme_deviation": [0.08, 0.10, 0.12, 0.15],
        "reclaim_scan_start": [20, 35, 50, 65],
        "reclaim_scan_end": [90, 120, 150, 180],
        "hold_seconds": [2, 4, 6, 8],
        "hold_buffer": [0.005, 0.01, 0.015, 0.02],
        "post_reclaim_move": [0.01, 0.02, 0.03],
        "stop_loss": [0.25, 0.30, 0.35, 0.40, 0.45],
        "take_profit": [0.60, 0.65, 0.70, 0.75, 0.80],
    }
