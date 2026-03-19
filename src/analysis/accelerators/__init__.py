"""Registry for accelerated strategy optimization kernels."""

from __future__ import annotations

from analysis.accelerators.base import PrecomputedDataset, StrategyKernel
from analysis.accelerators.s1 import S1Accelerator
from analysis.accelerators.s2_s6 import (
    S2Accelerator,
    S3Accelerator,
    S4Accelerator,
    S5Accelerator,
    S6Accelerator,
)
from analysis.accelerators.s7_s12 import (
    S7Accelerator,
    S8Accelerator,
    S9Accelerator,
    S10Accelerator,
    S11Accelerator,
    S12Accelerator,
)

_REGISTRY: dict[str, StrategyKernel] = {
    "S1": S1Accelerator(),
    "S2": S2Accelerator(),
    "S3": S3Accelerator(),
    "S4": S4Accelerator(),
    "S5": S5Accelerator(),
    "S6": S6Accelerator(),
    "S7": S7Accelerator(),
    "S8": S8Accelerator(),
    "S9": S9Accelerator(),
    "S10": S10Accelerator(),
    "S11": S11Accelerator(),
    "S12": S12Accelerator(),
}


def get_strategy_kernel(strategy_id: str) -> StrategyKernel | None:
    """Return the registered accelerator kernel for a strategy, if any."""
    return _REGISTRY.get(strategy_id)


def has_strategy_kernel(strategy_id: str) -> bool:
    """Return whether a strategy has an accelerator kernel."""
    return strategy_id in _REGISTRY


__all__ = [
    "PrecomputedDataset",
    "StrategyKernel",
    "get_strategy_kernel",
    "has_strategy_kernel",
]
