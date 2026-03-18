"""TEMPLATE strategy configuration — copy and customize for new strategies.

Rename this module's class and replace the example fields with your strategy's
real parameters.  Keep ``get_default_config()`` returning an instance with
sensible production defaults.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S4Config(StrategyConfig):
    """Configuration for S4 (Volatility Regime) strategy.

    Detect high-volatility regimes and enter contrarian when price is extreme.
    """

    # Rolling lookback window for volatility calculation (seconds)
    lookback_window: int = 60

    # Minimum volatility (std dev) threshold to consider high-vol regime
    vol_threshold: float = 0.08

    # Evaluation time point (seconds since market start)
    eval_second: int = 120

    # Price below this is considered extreme low
    extreme_price_low: float = 0.30

    # Price above this is considered extreme high
    extreme_price_high: float = 0.70


def get_default_config() -> S4Config:
    """Return the production-default S4 configuration.

    TODO: Update ``strategy_id`` to your folder name (e.g. ``'S3'``)
          and ``strategy_name`` to a descriptive slug (e.g. ``'S3_momentum'``).
    """
    return S4Config(
        strategy_id="S4",
        strategy_name="S4_volatility",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S4 strategy.

    The optimizer generates the Cartesian product of all parameter values
    and backtests every combination.

    Grid size: 3×3×3×2×2 = 108 combinations
    """
    return {
        "lookback_window": [30, 60, 90],
        "vol_threshold": [0.05, 0.08, 0.10],
        "eval_second": [60, 120, 180],
        "extreme_price_low": [0.25, 0.30],
        "extreme_price_high": [0.70, 0.75],
    }
