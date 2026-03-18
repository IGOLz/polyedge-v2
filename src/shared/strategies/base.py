from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np


@dataclass
class StrategyConfig:
    """Configuration for a strategy instance."""

    strategy_id: str  # 'S1', 'S2', etc.
    strategy_name: str  # 'S1_spike_reversion'
    enabled: bool = True


@dataclass
class MarketSnapshot:
    """Point-in-time view of a market for strategy evaluation.

    ``prices`` is a numpy ndarray indexed by elapsed second, with NaN for
    missing ticks. It contains only the history available at evaluation time.
    ``elapsed_seconds`` gives the current position in the market so strategies
    can determine how much data is available. ``feature_series`` optionally
    carries aligned per-second arrays such as underlying crypto returns or
    volatility measures.
    """

    market_id: str
    market_type: str
    prices: np.ndarray  # up_price indexed by elapsed second, NaN for missing
    total_seconds: int  # total market duration in seconds
    elapsed_seconds: float  # current position in market (for live: time since start)
    feature_series: dict[str, np.ndarray] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)  # asset, hour, started_at, etc.


@dataclass
class Signal:
    """Trade signal emitted by a strategy.

    The strategy's ``evaluate()`` populates ``direction``, ``strategy_name``,
    ``entry_price``, and strategy-specific ``signal_data`` keys.  The
    ``locked_*`` fields and execution ``signal_data`` keys (``bet_cost``,
    ``shares``, etc.) are populated by the trading adapter, not here.
    """

    direction: str  # 'Up' or 'Down'
    strategy_name: str
    entry_price: float
    signal_data: dict[str, Any] = field(default_factory=dict)
    confidence_multiplier: float = 1.0
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    locked_shares: int = 0
    locked_cost: float = 0.0
    locked_balance: float = 0.0
    locked_bet_size: float = 0.0


class BaseStrategy(ABC):
    """Abstract base for all strategies.

    Subclasses implement ``evaluate()`` as a pure, synchronous signal
    detector.  No side effects, no async, no database access.
    """

    config: StrategyConfig

    def __init__(self, config: StrategyConfig):
        self.config = config

    def required_feature_columns(self) -> tuple[str, ...]:
        """Return aligned feature columns required by this strategy."""
        return ()

    def market_is_eligible(self, market: dict) -> bool:
        """Return whether *market* has the required aligned feature data."""
        required = self.required_feature_columns()
        if not required:
            return True

        feature_series = market.get("feature_series", {})
        for column in required:
            series = feature_series.get(column)
            if series is None or not np.any(np.isfinite(series)):
                return False
        return True

    @abstractmethod
    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Pure signal detection. No side effects, no async, no DB."""
        ...
