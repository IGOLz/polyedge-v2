from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S13Config(StrategyConfig):
    """Configuration for S13 underlying lag follow."""

    feature_window: int = 5
    entry_window_start: int = 20
    entry_window_end: int = 240
    min_underlying_return: float = 0.001
    min_market_confirmation: float = 0.0
    max_market_delta: float = 0.05
    max_price_distance_from_mid: float = 0.2
    max_underlying_vol: float = 0.006
    live_stop_loss_price: float = 0.25
    live_take_profit_price: float = 0.80


def get_candidate_config() -> S13Config:
    return S13Config(
        strategy_id="S13",
        strategy_name="S13_underlying_lag_follow",
    )


def get_default_config() -> S13Config:
    return get_candidate_config()


def get_param_grid() -> dict[str, list]:
    return {
        "feature_window": [5, 10, 30],
        "entry_window_start": [10, 20, 30, 45],
        "entry_window_end": [90, 120, 180, 240],
        "min_underlying_return": [0.0005, 0.001, 0.0015, 0.002],
        "min_market_confirmation": [0.0, 0.003, 0.005, 0.008],
        "max_market_delta": [0.03, 0.05, 0.07, 0.10],
        "max_price_distance_from_mid": [0.08, 0.12, 0.16, 0.20],
        "max_underlying_vol": [0.006, 0.01, 0.015, 0.02],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.65, 0.70, 0.75, 0.80],
    }
