from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S16Config(StrategyConfig):
    """Configuration for S16 underlying reversal catch-up."""

    short_window: int = 5
    long_window: int = 30
    entry_window_start: int = 20
    entry_window_end: int = 240
    min_short_return: float = 0.001
    min_long_return_opposite: float = 0.0015
    min_price_distance_from_mid: float = 0.06
    max_underlying_vol: float = 0.02


def get_default_config() -> S16Config:
    return S16Config(
        strategy_id="S16",
        strategy_name="S16_underlying_reversal_catchup",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "short_window": [5, 10],
        "long_window": [10, 30],
        "entry_window_start": [10, 20, 30, 45],
        "entry_window_end": [90, 120, 180, 240],
        "min_short_return": [0.0005, 0.001, 0.0015, 0.002],
        "min_long_return_opposite": [0.001, 0.0015, 0.002, 0.003],
        "min_price_distance_from_mid": [0.04, 0.06, 0.08, 0.10],
        "max_underlying_vol": [0.008, 0.012, 0.016, 0.02],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.60, 0.65, 0.70, 0.75],
    }
