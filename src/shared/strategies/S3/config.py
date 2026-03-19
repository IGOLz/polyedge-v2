"""S3 strategy configuration."""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S3Config(StrategyConfig):
    """Configuration for S3 mean reversion."""

    spike_threshold: float = 0.80
    spike_lookback: int = 15
    reversion_pct: float = 0.15
    min_reversion_sec: int = 60
    entry_window_start: int = 5
    entry_window_end: int = 180
    min_seconds_since_extremum: int = 3
    min_distance_from_mid: float = 0.10
    live_stop_loss_price: float = 0.18
    live_take_profit_price: float = 0.85


def get_default_config() -> S3Config:
    """Return the production-default S3 configuration."""
    return S3Config(
        strategy_id="S3",
        strategy_name="S3_reversion",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S3."""
    return {
        "spike_threshold": [0.78, 0.80, 0.82],
        "spike_lookback": [15, 30],
        "reversion_pct": [0.12, 0.15, 0.18],
        "min_reversion_sec": [45, 60, 90],
        "entry_window_start": [5, 15],
        "entry_window_end": [120, 180, 240],
        "min_seconds_since_extremum": [2, 3, 5],
        "min_distance_from_mid": [0.08, 0.10, 0.12],
        # Stop loss and take profit are token-side price thresholds.
        # For Up trades they apply to the yes token; for Down trades they
        # apply to the no token.
        "stop_loss": [0.15, 0.18, 0.20],
        "take_profit": [0.80, 0.85],
    }
