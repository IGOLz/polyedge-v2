from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S20Config(StrategyConfig):
    """Configuration for S20 EVcurve-style checkpoint continuation."""

    checkpoint_tolerance: int = 2
    min_underlying_return_from_open: float = 0.0015
    min_recent_return_5s: float = 0.0006
    underlying_beta: float = 18.0
    min_directional_gap: float = 0.012
    min_market_delta_from_open: float = 0.01
    max_entry_price: float = 0.78


def get_default_config() -> S20Config:
    return S20Config(
        strategy_id="S20",
        strategy_name="S20_checkpoint_curve_follow",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "checkpoint_tolerance": [1, 2, 3],
        "min_underlying_return_from_open": [0.001, 0.0015, 0.0025],
        "min_recent_return_5s": [0.0003, 0.0006, 0.001],
        "underlying_beta": [12.0, 18.0, 24.0],
        "min_directional_gap": [0.008, 0.012, 0.016, 0.02],
        "min_market_delta_from_open": [0.005, 0.01, 0.015],
        "max_entry_price": [0.68, 0.74, 0.80, 0.86],
        "stop_loss": [0.20, 0.25, 0.30],
        "take_profit": [0.70, 0.75, 0.80],
    }


def get_quick_param_grid() -> dict[str, list]:
    """Return a coarse S20 grid for fast first-pass exploration.

    Total combinations: 512
    """
    return {
        "checkpoint_tolerance": [1, 2],
        "min_underlying_return_from_open": [0.001, 0.0025],
        "min_recent_return_5s": [0.0003, 0.001],
        "underlying_beta": [12.0, 24.0],
        "min_directional_gap": [0.008, 0.016],
        "min_market_delta_from_open": [0.005, 0.015],
        "max_entry_price": [0.68, 0.80],
        "stop_loss": [0.20, 0.30],
        "take_profit": [0.70, 0.80],
    }
