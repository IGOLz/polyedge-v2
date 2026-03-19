from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S5Config(StrategyConfig):
    """Configuration for S5 time-phase midpoint reclaim."""

    entry_window_start: int = 45
    entry_window_end: int = 180
    allowed_hours: list[int] | None = None
    allowed_assets: list[str] | None = None
    allowed_durations_minutes: list[int] | None = None
    price_range_low: float = 0.45
    price_range_high: float = 0.60
    approach_lookback: int = 8
    cross_buffer: float = 0.02
    confirmation_lookback: int = 4
    confirmation_min_move: float = 0.015
    min_cross_move: float = 0.05
    live_stop_loss_price: float = 0.35
    live_take_profit_price: float = 0.70


def get_default_config() -> S5Config:
    return S5Config(
        strategy_id="S5",
        strategy_name="S5_time_phase_midpoint_reclaim",
        allowed_hours=[18, 19, 20, 21, 22, 23],
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [45, 60],
        "entry_window_end": [180, 240],
        "allowed_hours": [
            None,
            [13, 14, 15, 16, 17, 18],
            [18, 19, 20, 21, 22, 23],
        ],
        "price_range_low": [0.45, 0.47],
        "price_range_high": [0.58, 0.60],
        "approach_lookback": [8, 12],
        "cross_buffer": [0.015, 0.02],
        "confirmation_lookback": [3, 5],
        "confirmation_min_move": [0.01, 0.015],
        "min_cross_move": [0.04, 0.05],
        "stop_loss": [0.30, 0.35],
        "take_profit": [0.65, 0.70],
    }
