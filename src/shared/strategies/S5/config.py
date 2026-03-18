from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S5Config(StrategyConfig):
    """Configuration for S5 time-phase midpoint reclaim."""

    entry_window_start: int = 45
    entry_window_end: int = 180
    allowed_hours: list[int] | None = None
    price_range_low: float = 0.42
    price_range_high: float = 0.58
    approach_lookback: int = 8
    cross_buffer: float = 0.01


def get_default_config() -> S5Config:
    return S5Config(
        strategy_id="S5",
        strategy_name="S5_time_phase_midpoint_reclaim",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [20, 45, 60, 90],
        "entry_window_end": [90, 120, 180, 240],
        "allowed_hours": [
            None,
            [8, 9, 10, 11, 12, 13],
            [13, 14, 15, 16, 17, 18],
            [18, 19, 20, 21, 22, 23],
        ],
        "price_range_low": [0.40, 0.42, 0.45, 0.47],
        "price_range_high": [0.53, 0.55, 0.58, 0.60],
        "approach_lookback": [4, 6, 8, 12],
        "cross_buffer": [0.005, 0.01, 0.015, 0.02],
        "stop_loss": [0.25, 0.30, 0.35, 0.40],
        "take_profit": [0.60, 0.65, 0.70, 0.75],
    }
