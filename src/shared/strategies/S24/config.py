from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S24Config(StrategyConfig):
    """Configuration for S24 premarket-inspired opening drive accumulation."""

    entry_window_start: int = 5
    entry_window_end: int = 45
    min_underlying_return_from_open: float = 0.001
    min_recent_return_5s: float = 0.0006
    min_market_delta_from_open: float = 0.0
    max_market_delta_from_open: float = 0.03
    min_trade_count: float = 20.0
    min_volume: float = 0.1
    max_entry_price: float = 0.75


def get_default_config() -> S24Config:
    return S24Config(
        strategy_id="S24",
        strategy_name="S24_opening_drive_accumulate",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [3, 5, 10],
        "entry_window_end": [20, 30, 45],
        "min_underlying_return_from_open": [0.0005, 0.001, 0.0015],
        "min_recent_return_5s": [0.0003, 0.0006, 0.001],
        "min_market_delta_from_open": [0.0, 0.005],
        "max_market_delta_from_open": [0.02, 0.03, 0.04],
        "min_trade_count": [10.0, 20.0, 40.0],
        "min_volume": [0.0, 0.1],
        "max_entry_price": [0.65, 0.75, 0.85],
        "stop_loss": [0.20, 0.30],
        "take_profit": [0.70, 0.80],
    }


def get_quick_param_grid() -> dict[str, list]:
    """Return a coarse S24 grid for fast first-pass exploration.

    Total combinations: 2048
    """
    return {
        "entry_window_start": [3, 10],
        "entry_window_end": [20, 45],
        "min_underlying_return_from_open": [0.0005, 0.0015],
        "min_recent_return_5s": [0.0003, 0.001],
        "min_market_delta_from_open": [0.0, 0.005],
        "max_market_delta_from_open": [0.02, 0.04],
        "min_trade_count": [10.0, 40.0],
        "min_volume": [0.0, 0.1],
        "max_entry_price": [0.65, 0.85],
        "stop_loss": [0.20, 0.30],
        "take_profit": [0.70, 0.80],
    }
