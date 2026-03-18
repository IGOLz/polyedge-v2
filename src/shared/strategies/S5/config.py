"""TEMPLATE strategy configuration — copy and customize for new strategies.

Rename this module's class and replace the example fields with your strategy's
real parameters.  Keep ``get_default_config()`` returning an instance with
sensible production defaults.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S5Config(StrategyConfig):
    """Configuration for S5 (Time-Phase Entry) strategy.

    Enter when current time falls within allowed window AND price is in target range.
    Exploits patterns where certain time phases have better entry success.
    """

    # Entry window start time (seconds since market start)
    entry_window_start: int = 60

    # Entry window end time (seconds since market start)
    entry_window_end: int = 180

    # Optional hour-of-day filter (None = all hours allowed)
    allowed_hours: list[int] | None = None

    # Price range low bound (entry when price in this range)
    price_range_low: float = 0.45

    # Price range high bound (entry when price in this range)
    price_range_high: float = 0.55


def get_default_config() -> S5Config:
    """Return the production-default S5 configuration.

    TODO: Update ``strategy_id`` to your folder name (e.g. ``'S3'``)
          and ``strategy_name`` to a descriptive slug (e.g. ``'S3_momentum'``).
    """
    return S5Config(
        strategy_id="S5",
        strategy_name="S5_time_phase",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S5 strategy.

    The optimizer generates the Cartesian product of all parameter values
    and backtests every combination.

    Grid size: 3×3×3×2×2×3×3 = 972 combinations
    """
    return {
        "entry_window_start": [30, 60, 90],
        "entry_window_end": [120, 180, 240],
        "allowed_hours": [None, [10, 11, 12, 13, 14, 15], [14, 15, 16, 17, 18]],
        "price_range_low": [0.40, 0.45],
        "price_range_high": [0.55, 0.60],
        # Stop loss and take profit are absolute price thresholds (not relative offsets).
        # Entry prices 0.45-0.60 depending on time phase.
        # Engine handles direction logic (swap SL/TP for Down bets).
        "stop_loss": [0.35, 0.40, 0.45],
        "take_profit": [0.65, 0.70, 0.75],
    }
