"""S3 strategy configuration."""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S3Config(StrategyConfig):
    """Configuration for S3 mean reversion."""

    spike_threshold: float = 0.75
    spike_lookback: int = 30
    reversion_pct: float = 0.10
    min_reversion_sec: int = 60


def get_default_config() -> S3Config:
    """Return the production-default S3 configuration."""
    return S3Config(
        strategy_id="S3",
        strategy_name="S3_reversion",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S3."""
    return {
        "spike_threshold": [0.70, 0.75, 0.80, 0.85],
        "spike_lookback": [15, 30, 60],
        "reversion_pct": [0.05, 0.08, 0.10, 0.15],
        "min_reversion_sec": [30, 60, 120],
        # Stop loss and take profit are token-side price thresholds.
        # For Up trades they apply to the yes token; for Down trades they
        # apply to the no token.
        "stop_loss": [0.15, 0.20, 0.25],
        "take_profit": [0.75, 0.80, 0.85],
    }
