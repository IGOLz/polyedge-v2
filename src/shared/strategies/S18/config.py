from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S18Config(StrategyConfig):
    """Configuration for S18 multi-window acceleration follow."""

    entry_window_start: int = 20
    entry_window_end: int = 180
    min_return_30s: float = 0.0015
    min_return_10s: float = 0.001
    min_return_5s: float = 0.0007
    acceleration_ratio: float = 0.6
    max_underlying_vol: float = 0.015
    min_trade_count: float = 10.0
    max_price_distance_from_mid: float = 0.18


def get_default_config() -> S18Config:
    return S18Config(
        strategy_id="S18",
        strategy_name="S18_acceleration_follow",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [10, 20, 30, 45],
        "entry_window_end": [90, 120, 180, 240],
        "min_return_30s": [0.001, 0.0015, 0.002, 0.003],
        "min_return_10s": [0.0006, 0.001, 0.0014, 0.0018],
        "min_return_5s": [0.0004, 0.0007, 0.001, 0.0014],
        "acceleration_ratio": [0.4, 0.6, 0.8, 1.0],
        "max_underlying_vol": [0.008, 0.012, 0.016, 0.02],
        "min_trade_count": [5.0, 10.0, 20.0, 40.0],
        "max_price_distance_from_mid": [0.08, 0.12, 0.16, 0.20],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.65, 0.70, 0.75, 0.80],
    }
