from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S19Config(StrategyConfig):
    """Configuration for S19 aggressor-flow confirmation."""

    entry_window_start: int = 10
    entry_window_end: int = 180
    feature_window: int = 5
    min_underlying_return: float = 0.0007
    min_market_delta: float = 0.002
    max_market_delta: float = 0.04
    min_trade_count: float = 10.0
    min_volume: float = 0.0
    buy_imbalance_threshold: float = 0.20
    max_price_distance_from_mid: float = 0.18


def get_default_config() -> S19Config:
    return S19Config(
        strategy_id="S19",
        strategy_name="S19_aggressor_flow",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [10, 20, 30, 45],
        "entry_window_end": [90, 120, 180, 240],
        "feature_window": [5, 10, 30],
        "min_underlying_return": [0.0005, 0.001, 0.0015, 0.002],
        "min_market_delta": [0.0, 0.002, 0.004, 0.006],
        "max_market_delta": [0.02, 0.04, 0.06, 0.08],
        "min_trade_count": [5.0, 10.0, 20.0, 40.0],
        "min_volume": [0.0, 0.1, 0.5, 1.0],
        "buy_imbalance_threshold": [0.10, 0.20, 0.30, 0.40],
        "max_price_distance_from_mid": [0.08, 0.12, 0.16, 0.20],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.65, 0.70, 0.75, 0.80],
    }
