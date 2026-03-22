from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S25Config(StrategyConfig):
    """Configuration for S25 S20-lite checkpoint drift follow."""

    checkpoint_tolerance: int = 2
    min_underlying_return_5s: float = 0.0006
    underlying_beta: float = 12.0
    min_directional_gap: float = 0.008
    min_market_delta_5s: float = 0.002
    min_trade_count: float = 15.0
    min_price_distance_from_mid: float = 0.05
    max_entry_price: float = 0.78


def get_default_config() -> S25Config:
    return S25Config(
        strategy_id="S25",
        strategy_name="S25_s20_lite_checkpoint_drift",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "checkpoint_tolerance": [1, 2, 3],
        "min_underlying_return_5s": [0.0003, 0.0006, 0.001],
        "underlying_beta": [8.0, 12.0, 16.0, 20.0],
        "min_directional_gap": [0.004, 0.008, 0.012],
        "min_market_delta_5s": [0.0, 0.002, 0.004],
        "min_trade_count": [5.0, 15.0, 30.0],
        "min_price_distance_from_mid": [0.02, 0.05, 0.08],
        "max_entry_price": [0.68, 0.78, 0.88],
        "stop_loss": [0.20, 0.30],
        "take_profit": [0.70, 0.80],
    }


def get_quick_param_grid() -> dict[str, list]:
    """Return a coarse S25 grid for fast first-pass exploration.

    Total combinations: 1024
    """
    return {
        "checkpoint_tolerance": [1, 2],
        "min_underlying_return_5s": [0.0003, 0.001],
        "underlying_beta": [8.0, 16.0],
        "min_directional_gap": [0.004, 0.012],
        "min_market_delta_5s": [0.0, 0.004],
        "min_trade_count": [5.0, 30.0],
        "min_price_distance_from_mid": [0.02, 0.08],
        "max_entry_price": [0.68, 0.88],
        "stop_loss": [0.20, 0.30],
        "take_profit": [0.70, 0.80],
    }
