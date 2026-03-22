from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S21Config(StrategyConfig):
    """Configuration for S21 endgame sweep continuation."""

    max_seconds_to_close: int = 60
    min_seconds_to_close: int = 3
    min_underlying_return_from_open: float = 0.0015
    min_recent_underlying_return_5s: float = 0.0007
    min_recent_market_delta_5s: float = 0.008
    min_market_delta_from_open: float = 0.02
    min_trade_count: float = 20.0
    max_entry_price: float = 0.82


def get_default_config() -> S21Config:
    return S21Config(
        strategy_id="S21",
        strategy_name="S21_endgame_sweep_follow",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "max_seconds_to_close": [30, 60, 90],
        "min_seconds_to_close": [1, 3, 5],
        "min_underlying_return_from_open": [0.001, 0.0015, 0.0025],
        "min_recent_underlying_return_5s": [0.0005, 0.001, 0.0015],
        "min_recent_market_delta_5s": [0.005, 0.01, 0.015],
        "min_market_delta_from_open": [0.01, 0.02, 0.03],
        "min_trade_count": [10.0, 20.0, 40.0],
        "max_entry_price": [0.70, 0.78, 0.86],
        "stop_loss": [0.20, 0.25, 0.30],
        "take_profit": [0.70, 0.75, 0.80],
    }


def get_quick_param_grid() -> dict[str, list]:
    """Return a coarse S21 grid for fast first-pass exploration.

    Total combinations: 1024
    """
    return {
        "max_seconds_to_close": [30, 90],
        "min_seconds_to_close": [1, 5],
        "min_underlying_return_from_open": [0.001, 0.0025],
        "min_recent_underlying_return_5s": [0.0005, 0.0015],
        "min_recent_market_delta_5s": [0.005, 0.015],
        "min_market_delta_from_open": [0.01, 0.03],
        "min_trade_count": [10.0, 40.0],
        "max_entry_price": [0.70, 0.86],
        "stop_loss": [0.20, 0.30],
        "take_profit": [0.70, 0.80],
    }
