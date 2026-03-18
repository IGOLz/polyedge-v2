"""Shared data models used across all services."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MarketState:
    """Tracks the live state of a single open market (used by core + trading)."""
    market_id: str              # conditionId from Polymarket
    up_token_id: str            # token ID for the Up outcome
    down_token_id: str          # token ID for the Down outcome
    started_at: datetime        # market open time (UTC)
    ended_at: datetime          # market close time (UTC)
    market_type: Optional[str] = None
    latest_up_price: Optional[float] = None
    latest_volume: Optional[float] = None
    last_recorded_at: Optional[datetime] = None
    is_open: bool = True
    awaiting_resolution: bool = False
    tick_count: int = 0


@dataclass
class Tick:
    """A single price tick."""
    market_id: str
    time: datetime
    up_price: float
    down_price: float = 0.0  # derived as 1 - up_price

    def __post_init__(self):
        if self.down_price == 0.0:
            self.down_price = round(1.0 - self.up_price, 6)
