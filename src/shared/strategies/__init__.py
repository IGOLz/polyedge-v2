"""Shared strategy framework — types, base class, discovery registry, and reporting."""

from .base import BaseStrategy, MarketSnapshot, Signal, StrategyConfig
from .registry import discover_strategies, get_strategy
from .report import StrategyReport

__all__ = [
    "BaseStrategy",
    "StrategyConfig",
    "MarketSnapshot",
    "Signal",
    "StrategyReport",
    "discover_strategies",
    "get_strategy",
]
