from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S15Config(StrategyConfig):
    """Configuration for S15 breakout with underlying confirmation."""

    setup_window_end: int = 45
    breakout_scan_start: int = 50
    breakout_scan_end: int = 180
    breakout_buffer: float = 0.02
    confirmation_points: int = 2
    feature_window: int = 10
    min_underlying_return: float = 0.001
    min_trade_count: float = 20.0


def get_default_config() -> S15Config:
    return S15Config(
        strategy_id="S15",
        strategy_name="S15_breakout_with_underlying_confirmation",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "setup_window_end": [20, 30, 45, 60],
        "breakout_scan_start": [25, 40, 55, 70],
        "breakout_scan_end": [90, 120, 180, 240],
        "breakout_buffer": [0.01, 0.015, 0.02, 0.03],
        "confirmation_points": [1, 2, 3, 4],
        "feature_window": [5, 10, 30],
        "min_underlying_return": [0.0005, 0.001, 0.0015, 0.002],
        "min_trade_count": [5.0, 10.0, 20.0, 40.0],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.65, 0.70, 0.75, 0.80],
    }
