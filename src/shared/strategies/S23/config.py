from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S23Config(StrategyConfig):
    """Configuration for S23 EVSnipe-style trigger crossing."""

    entry_window_start: int = 5
    entry_window_end: int = 240
    trigger_return_from_open: float = 0.002
    pre_trigger_buffer: float = 0.0005
    min_recent_return_5s: float = 0.0006
    max_market_delta_from_open: float = 0.04
    min_trade_count: float = 10.0
    max_entry_price: float = 0.80


def get_default_config() -> S23Config:
    return S23Config(
        strategy_id="S23",
        strategy_name="S23_trigger_cross_snipe",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "entry_window_start": [5, 10, 20],
        "entry_window_end": [120, 180, 240],
        "trigger_return_from_open": [0.001, 0.0015, 0.002, 0.003],
        "pre_trigger_buffer": [0.0003, 0.0005, 0.001],
        "min_recent_return_5s": [0.0003, 0.0006, 0.001],
        "max_market_delta_from_open": [0.02, 0.04, 0.06],
        "min_trade_count": [5.0, 10.0, 20.0],
        "max_entry_price": [0.70, 0.80, 0.90],
        "stop_loss": [0.20, 0.25, 0.30],
        "take_profit": [0.70, 0.75, 0.80],
    }


def get_quick_param_grid() -> dict[str, list]:
    """Return a coarse S23 grid for fast first-pass exploration.

    Total combinations: 1024
    """
    return {
        "entry_window_start": [5, 20],
        "entry_window_end": [120, 240],
        "trigger_return_from_open": [0.001, 0.002],
        "pre_trigger_buffer": [0.0003, 0.001],
        "min_recent_return_5s": [0.0003, 0.001],
        "max_market_delta_from_open": [0.02, 0.06],
        "min_trade_count": [5.0, 20.0],
        "max_entry_price": [0.70, 0.90],
        "stop_loss": [0.20, 0.30],
        "take_profit": [0.70, 0.80],
    }
