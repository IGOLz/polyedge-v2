from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S4Config(StrategyConfig):
    """Configuration for S4 volatility-exhaustion fade."""

    lookback_window: int = 60
    vol_threshold: float = 0.025
    eval_second: int = 45
    extreme_price_low: float = 0.30
    extreme_price_high: float = 0.70
    reversal_lookback: int = 6
    reversal_min_move: float = 0.015


def get_default_config() -> S4Config:
    return S4Config(
        strategy_id="S4",
        strategy_name="S4_volatility_exhaustion_fade",
    )


def get_param_grid() -> dict[str, list]:
    return {
        "lookback_window": [20, 30, 45, 60, 90],
        "vol_threshold": [0.012, 0.018, 0.024, 0.03, 0.04],
        "eval_second": [20, 30, 45, 60, 90],
        "extreme_price_low": [0.20, 0.25, 0.30, 0.35],
        "extreme_price_high": [0.65, 0.70, 0.75, 0.80],
        "reversal_lookback": [3, 5, 8, 12],
        "reversal_min_move": [0.008, 0.012, 0.016, 0.02],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.65, 0.70, 0.75, 0.80],
    }
