from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S14Config(StrategyConfig):
    """Configuration for S14 divergence fade."""

    allowed_durations_minutes: list[int] | None = None
    feature_window: int = 30
    entry_window_start: int = 30
    entry_window_end: int = 240
    min_market_delta_abs: float = 0.06
    max_underlying_return_abs: float = 0.0015
    extreme_price_low: float = 0.35
    extreme_price_high: float = 0.65
    require_direction_mismatch: bool = True
    live_stop_loss_price: float = 0.25
    live_take_profit_price: float = 0.75


def get_baseline_config() -> S14Config:
    return S14Config(
        strategy_id="S14",
        strategy_name="S14_divergence_fade",
        feature_window=10,
        entry_window_start=20,
        entry_window_end=210,
        min_market_delta_abs=0.04,
        max_underlying_return_abs=0.0008,
        extreme_price_low=0.30,
        extreme_price_high=0.70,
        require_direction_mismatch=True,
        live_stop_loss_price=0.30,
        live_take_profit_price=0.70,
    )


def get_candidate_config() -> S14Config:
    """Return the next S14 research candidate to validate."""
    return S14Config(
        strategy_id="S14",
        strategy_name="S14_divergence_fade",
        allowed_durations_minutes=[5],
        feature_window=30,
        entry_window_start=30,
        entry_window_end=240,
        min_market_delta_abs=0.06,
        max_underlying_return_abs=0.0015,
        extreme_price_low=0.35,
        extreme_price_high=0.65,
        require_direction_mismatch=True,
        live_stop_loss_price=0.25,
        live_take_profit_price=0.75,
    )


def get_default_config() -> S14Config:
    return get_candidate_config()


def get_param_grid() -> dict[str, list]:
    return {
        "feature_window": [5, 10, 30],
        "entry_window_start": [10, 20, 30, 45],
        "entry_window_end": [90, 120, 180, 240],
        "min_market_delta_abs": [0.03, 0.04, 0.05, 0.06],
        "max_underlying_return_abs": [0.0005, 0.0008, 0.0012, 0.0015],
        "extreme_price_low": [0.20, 0.25, 0.30, 0.35],
        "extreme_price_high": [0.65, 0.70, 0.75, 0.80],
        "require_direction_mismatch": [True, False],
        "stop_loss": [0.20, 0.25, 0.30, 0.35],
        "take_profit": [0.60, 0.65, 0.70, 0.75],
    }
