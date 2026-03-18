"""Analysis constants — shared across all analysis modules."""

import numpy as np

# Checkpoint seconds for price trajectory analysis
CHECKPOINTS = [30, 60, 120, 180, 240, 300]

# Calibration parameters
PRICE_BUCKET_WIDTH = 0.05
MIN_BUCKET_SAMPLES = 5
MIN_TICKS_PER_MARKET = 10
SIGNIFICANCE_LEVEL = 0.15

# Default bet size for backtests
DEFAULT_BET_SIZE = 10
DEFAULT_FEE_RATE = 0.02


def to_python(val):
    """Convert numpy types to native Python types for psycopg2."""
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    return val
