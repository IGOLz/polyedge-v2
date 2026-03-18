"""S7 strategy configuration — composite ensemble with inline pattern detection.

S7 runs multiple detection patterns inline (calibration, momentum, volatility)
and returns a signal only when ≥ min_agreement patterns agree on direction.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class S7Config(StrategyConfig):
    """Configuration for S7 composite ensemble strategy.

    This strategy duplicates detection logic from S1 (calibration), S2 (momentum),
    and S4 (volatility) inline rather than calling those strategies. The pure
    function contract prevents accessing the registry or calling other strategies.
    """

    # Ensemble parameters
    min_agreement: int = 2  # minimum strategies that must agree on direction
    calibration_enabled: bool = True
    momentum_enabled: bool = True
    volatility_enabled: bool = True
    
    # Calibration pattern parameters (from S1)
    calibration_deviation: float = 0.08  # min deviation from 0.50 to trigger
    calibration_eval_window: int = 60    # seconds to scan for calibration signal
    
    # Momentum pattern parameters (from S2)
    momentum_threshold: float = 0.03     # min velocity to trigger
    momentum_eval_start: int = 30        # start of velocity measurement window
    momentum_eval_end: int = 60          # end of velocity measurement window
    
    # Volatility pattern parameters (from S4)
    volatility_threshold: float = 0.08   # min std dev to consider high vol
    volatility_lookback: int = 60        # lookback window for vol calculation
    volatility_eval_sec: int = 120       # when to evaluate vol + price
    extreme_price_low: float = 0.30      # low extreme threshold
    extreme_price_high: float = 0.70     # high extreme threshold


def get_default_config() -> S7Config:
    """Return the production-default S7 configuration."""
    return S7Config(
        strategy_id="S7",
        strategy_name="S7_composite",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for S7 composite ensemble.

    Explores ensemble configurations: which patterns to enable, agreement
    thresholds, and key thresholds for each detection pattern.

    Returns:
        Parameter grid with ~96 combinations.
    """
    return {
        "min_agreement": [2, 3],
        "calibration_enabled": [True, False],
        "momentum_enabled": [True, False],
        "volatility_enabled": [True, False],
        "calibration_deviation": [0.05, 0.08, 0.10],
        "momentum_threshold": [0.03, 0.05],
        "volatility_threshold": [0.08, 0.10],
    }
