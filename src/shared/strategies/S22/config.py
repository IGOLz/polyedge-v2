from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S22Config(StrategyConfig):
    """Configuration for S22 SessionBand-style late price bands."""

    max_seconds_to_close: int = 3
    min_seconds_to_close: int = 1
    min_lead_return_from_open: float = 0.001
    max_lead_return_from_open: float = 0.02
    min_recent_return_5s: float = 0.0005
    min_market_delta_from_open: float = 0.005
    min_trade_count: float = 10.0
    entry_price_floor: float = 0.60
    entry_price_cap: float = 0.92


def get_default_config() -> S22Config:
    return S22Config(
        strategy_id="S22",
        strategy_name="S22_session_band_hold",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "max_seconds_to_close": [2, 3, 5],
        "min_seconds_to_close": [1, 2, 3],
        "min_lead_return_from_open": [0.0008, 0.0015, 0.0025],
        "max_lead_return_from_open": [0.01, 0.02, 0.03],
        "min_recent_return_5s": [0.0003, 0.0006, 0.001],
        "min_market_delta_from_open": [0.0, 0.005, 0.01],
        "min_trade_count": [5.0, 10.0, 20.0],
        "entry_price_floor": [0.55, 0.65, 0.75],
        "entry_price_cap": [0.85, 0.90, 0.95],
        "stop_loss": [0.20, 0.25, 0.30],
        "take_profit": [0.70, 0.75, 0.80],
    }


def get_quick_param_grid() -> dict[str, list]:
    """Return a coarse S22 grid for fast first-pass exploration.

    Total combinations: 2048
    """
    return {
        "max_seconds_to_close": [2, 5],
        "min_seconds_to_close": [1, 3],
        "min_lead_return_from_open": [0.0008, 0.0025],
        "max_lead_return_from_open": [0.01, 0.03],
        "min_recent_return_5s": [0.0003, 0.001],
        "min_market_delta_from_open": [0.0, 0.01],
        "min_trade_count": [5.0, 20.0],
        "entry_price_floor": [0.55, 0.75],
        "entry_price_cap": [0.85, 0.95],
        "stop_loss": [0.20, 0.30],
        "take_profit": [0.70, 0.80],
    }
