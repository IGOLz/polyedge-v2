"""TEMPLATE strategy configuration — copy and customize for new strategies.

Rename this module's class and replace the example fields with your strategy's
real parameters.  Keep ``get_default_config()`` returning an instance with
sensible production defaults.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S1Config(StrategyConfig):
    """Configuration for S1 Calibration Mispricing strategy.
    
    Exploit systematic bias in 50/50 pricing by entering contrarian
    when price deviates significantly from balanced (0.50).
    """

    # Time window to scan for entry opportunities
    entry_window_start: int = 30  # seconds
    entry_window_end: int = 60  # seconds
    
    # Price deviation thresholds
    price_low_threshold: float = 0.45  # enter Up if price below this
    price_high_threshold: float = 0.55  # enter Down if price above this
    
    # Minimum deviation from 0.50 to trigger entry
    min_deviation: float = 0.08


def get_default_config() -> S1Config:
    """Return the production-default S1 configuration.

    TODO: Update ``strategy_id`` to your folder name (e.g. ``'S3'``)
          and ``strategy_name`` to a descriptive slug (e.g. ``'S3_momentum'``).
    """
    return S1Config(
        strategy_id="S1",
        strategy_name="S1_calibration",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S1 Calibration strategy.

    Tests various entry windows, price thresholds, and minimum deviations
    to find optimal calibration mispricing exploitation parameters.
    
    Total combinations: 3×3×2×2×3×3×3 = 972
    """
    return {
        "entry_window_start": [30, 45, 60],
        "entry_window_end": [60, 90, 120],
        "price_low_threshold": [0.40, 0.45],
        "price_high_threshold": [0.55, 0.60],
        "min_deviation": [0.05, 0.08, 0.10],
        # Stop loss and take profit are absolute price thresholds (not relative offsets).
        # Entry prices typically 0.45-0.55 for calibration mispricing strategy.
        # Engine handles direction logic (swap SL/TP for Down bets).
        "stop_loss": [0.35, 0.40, 0.45],
        "take_profit": [0.65, 0.70, 0.75],
    }
