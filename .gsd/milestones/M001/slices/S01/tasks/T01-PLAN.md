---
estimated_steps: 4
estimated_files: 3
---

# T01: Create base framework with dataclasses and registry

**Slice:** S01 — Shared strategy framework + data model
**Milestone:** M001

## Description

Create the foundational types and discovery mechanism for the shared strategy framework. This establishes the contract that all strategies, adapters, and consumers depend on. The four dataclasses (`StrategyConfig`, `MarketSnapshot`, `Signal`, `BaseStrategy`) define the boundary between strategy logic and execution infrastructure. The registry provides dynamic strategy discovery by scanning folder structure.

**Critical constraint — Signal backward compatibility (D006):** The `Signal` dataclass MUST include every field that `trading/executor.py` currently reads. The executor accesses these fields on Signal objects:
- `signal.direction` (str: 'Up' or 'Down')
- `signal.strategy_name` (str)
- `signal.entry_price` (float)
- `signal.signal_data` (dict with keys: `bet_cost`, `price_min`, `price_max`, `stop_loss_price`, `shares`, `actual_cost`, `current_balance`, `bet_size`, `balance_at_signal`, `profitability_thesis`)
- `signal.confidence_multiplier` (float, default 1.0)
- `signal.created_at` (datetime)
- `signal.locked_shares` (int, default 0)
- `signal.locked_cost` (float, default 0.0)
- `signal.locked_balance` (float, default 0.0)
- `signal.locked_bet_size` (float, default 0.0)

The strategy's `evaluate()` only sets `direction`, `strategy_name`, `entry_price`, and strategy-specific `signal_data` keys. The `locked_*` fields and execution `signal_data` keys are populated by the trading adapter (S03), not here.

## Steps

1. **Create `src/shared/strategies/base.py`** with these exact types:

   ```python
   from __future__ import annotations
   from abc import ABC, abstractmethod
   from dataclasses import dataclass, field
   from datetime import datetime, timezone
   from typing import Any
   import numpy as np

   @dataclass
   class StrategyConfig:
       strategy_id: str          # 'S1', 'S2', etc.
       strategy_name: str        # 'S1_spike_reversion'
       enabled: bool = True

   @dataclass
   class MarketSnapshot:
       market_id: str
       market_type: str
       prices: np.ndarray        # up_price indexed by elapsed second, NaN for missing
       total_seconds: int        # total market duration in seconds
       elapsed_seconds: float    # current position in market (for live: time since start)
       metadata: dict = field(default_factory=dict)  # asset, hour, started_at, etc.

   @dataclass
   class Signal:
       direction: str             # 'Up' or 'Down'
       strategy_name: str
       entry_price: float
       signal_data: dict[str, Any] = field(default_factory=dict)
       confidence_multiplier: float = 1.0
       created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
       locked_shares: int = 0
       locked_cost: float = 0.0
       locked_balance: float = 0.0
       locked_bet_size: float = 0.0

   class BaseStrategy(ABC):
       config: StrategyConfig

       def __init__(self, config: StrategyConfig):
           self.config = config

       @abstractmethod
       def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
           """Pure signal detection. No side effects, no async, no DB."""
           ...
   ```

2. **Create `src/shared/strategies/registry.py`** with dynamic discovery:

   ```python
   import importlib
   import pkgutil
   from pathlib import Path
   from .base import BaseStrategy, StrategyConfig

   _registry: dict[str, type[BaseStrategy]] = {}

   def discover_strategies() -> dict[str, type[BaseStrategy]]:
       """Scan shared/strategies/*/strategy.py for BaseStrategy subclasses."""
       strategies_dir = Path(__file__).parent
       _registry.clear()
       for item in sorted(strategies_dir.iterdir()):
           if not item.is_dir() or item.name.startswith(('_', '.')):
               continue
           strategy_module_path = item / 'strategy.py'
           if not strategy_module_path.exists():
               continue
           module_name = f"shared.strategies.{item.name}.strategy"
           try:
               module = importlib.import_module(module_name)
               for attr_name in dir(module):
                   attr = getattr(module, attr_name)
                   if (isinstance(attr, type)
                       and issubclass(attr, BaseStrategy)
                       and attr is not BaseStrategy):
                       _registry[item.name] = attr
                       break
           except Exception:
               continue  # skip broken strategy modules
       return dict(_registry)

   def get_strategy(strategy_id: str) -> BaseStrategy:
       """Instantiate a strategy by ID. Discovers if registry is empty."""
       if not _registry:
           discover_strategies()
       if strategy_id not in _registry:
           raise KeyError(f"Strategy '{strategy_id}' not found. Available: {list(_registry.keys())}")
       strategy_cls = _registry[strategy_id]
       # Strategy class must define a default config via its module's get_default_config()
       config_module_name = f"shared.strategies.{strategy_id}.config"
       config_module = importlib.import_module(config_module_name)
       config = config_module.get_default_config()
       return strategy_cls(config)
   ```

3. **Create `src/shared/strategies/__init__.py`** re-exporting public API:

   ```python
   from .base import BaseStrategy, StrategyConfig, MarketSnapshot, Signal
   from .registry import discover_strategies, get_strategy

   __all__ = [
       "BaseStrategy", "StrategyConfig", "MarketSnapshot", "Signal",
       "discover_strategies", "get_strategy",
   ]
   ```

4. **Verify imports work** by running:
   ```bash
   cd src && python -c "from shared.strategies import BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy; print('imports: PASS')"
   ```
   Also verify Signal has all required fields:
   ```bash
   cd src && python -c "
   from shared.strategies import Signal
   s = Signal(direction='Up', strategy_name='test', entry_price=0.5)
   assert hasattr(s, 'locked_shares') and s.locked_shares == 0
   assert hasattr(s, 'locked_cost') and s.locked_cost == 0.0
   assert hasattr(s, 'locked_balance') and s.locked_balance == 0.0
   assert hasattr(s, 'locked_bet_size') and s.locked_bet_size == 0.0
   assert hasattr(s, 'signal_data') and s.signal_data == {}
   assert hasattr(s, 'confidence_multiplier') and s.confidence_multiplier == 1.0
   assert s.created_at is not None
   print('Signal fields: PASS')
   "
   ```

## Must-Haves

- [ ] `StrategyConfig` dataclass with `strategy_id`, `strategy_name`, `enabled`
- [ ] `MarketSnapshot` dataclass with `prices: np.ndarray`, `elapsed_seconds`, `total_seconds`, `market_id`, `market_type`, `metadata`
- [ ] `Signal` dataclass with ALL 10 executor-required fields and correct defaults
- [ ] `BaseStrategy` ABC with synchronous `evaluate(snapshot) -> Signal | None`
- [ ] `discover_strategies()` returns dict of strategy_id → strategy class
- [ ] `get_strategy(id)` returns instantiated strategy
- [ ] `__init__.py` re-exports all 6 public names
- [ ] Zero imports from `trading.*`, `analysis.*`, or `core.*`

## Verification

- `cd src && python -c "from shared.strategies import BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy; print('imports: PASS')"` succeeds
- `cd src && python -c "from shared.strategies import Signal; s = Signal(direction='Up', strategy_name='test', entry_price=0.5); assert s.locked_shares == 0; assert s.locked_bet_size == 0.0; print('Signal defaults: PASS')"` succeeds
- `cd src && python -c "from shared.strategies import discover_strategies; d = discover_strategies(); print(f'discovered: {d}'); print('registry: PASS')"` succeeds (empty dict since S1 not yet created)
- `cd src && grep -r "from trading\|from analysis\|from core" shared/strategies/ && echo 'FAIL: forbidden imports' || echo 'no forbidden imports: PASS'`

## Observability Impact

- **New diagnostic surface:** `discover_strategies()` return value serves as the primary inspection point — shows which strategy IDs loaded successfully. Empty dict means no strategy folders found or all failed to import.
- **Error path:** `get_strategy('UNKNOWN')` raises `KeyError` with message listing all available strategy IDs. This structured error enables callers to diagnose misconfiguration without inspecting internal state.
- **Silent skip behavior:** Registry silently skips folders without `strategy.py` and modules that fail to import. This is intentional for resilience but means missing strategies are only visible by comparing expected vs actual registry keys. Future tasks may add optional logging.
- **How to inspect:** `python -c "from shared.strategies import discover_strategies; print(discover_strategies())"` from `src/` shows all discovered strategies.

## Inputs

- Research doc (S01-RESEARCH.md) — data model design, Signal field list, registry design
- `src/trading/strategies.py` lines 23-33 — reference for Signal fields (DO NOT import, only copy field names)
- `src/trading/executor.py` — reference for which Signal fields are accessed (DO NOT import)

## Expected Output

- `src/shared/strategies/__init__.py` — package with re-exports
- `src/shared/strategies/base.py` — four types: StrategyConfig, MarketSnapshot, Signal, BaseStrategy
- `src/shared/strategies/registry.py` — discover_strategies() and get_strategy()
