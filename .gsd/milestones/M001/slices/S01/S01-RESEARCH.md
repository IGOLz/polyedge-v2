# S01 — Shared Strategy Framework + Data Model — Research

**Date:** 2026-03-18
**Depth:** Targeted — known patterns applied to known codebase, no unfamiliar tech

## Summary

S01 creates the shared strategy framework: base classes (`StrategyConfig`, `BaseStrategy`, `MarketSnapshot`, `Signal`), a folder-based registry, and S1 (spike reversion) ported as proof. The codebase already has all the pieces — trading strategies in `trading/strategies.py`, analysis strategies in `analysis/backtest/module_3_mean_reversion.py` and `module_4_volatility.py`, and a `shared/` package at `src/shared/`. The work is straightforward dataclass + abstract class design with zero external dependencies beyond numpy (already used).

The critical constraint is **Signal backward compatibility** — the executor in `trading/executor.py` imports `Signal` from `trading.strategies` and reads 10+ fields including `locked_shares`, `locked_cost`, `locked_balance`, `locked_bet_size`, `signal_data` (dict with ~15 keys), `confidence_multiplier`, and `created_at`. The shared Signal must be a superset of this shape. The executor must NOT be modified (R009).

The second constraint is **MarketSnapshot format** — analysis already uses elapsed-seconds-indexed numpy arrays (via `data_loader.py`), so MarketSnapshot wraps this existing format. Trading's `list[Tick]` indexed by position is the bug source — the trading adapter (S03, not this slice) will convert ticks to MarketSnapshot.

## Recommendation

Build `shared/strategies/` as a pure-Python package with no async, no DB, no service-specific imports. Four files for the base layer (`base.py`, `registry.py`), one folder for S1 (`S1/config.py`, `S1/strategy.py`). The registry discovers strategies by scanning `shared/strategies/*/strategy.py` for `BaseStrategy` subclasses.

Port the **analysis** version of M3 (from `module_3_mean_reversion.py`) as S1's evaluate logic — it already operates on numpy arrays indexed by elapsed seconds, which matches MarketSnapshot. The trading version has async calls, balance checks, and bet sizing mixed into strategy logic — those are execution concerns, not strategy concerns.

StrategyConfig should be a plain dataclass holding the parameters currently in `trading/constants.py` M3_CONFIG. BaseStrategy.evaluate() takes a MarketSnapshot and returns `Signal | None`. No bet sizing, no balance checks, no DB queries — pure signal detection.

## Implementation Landscape

### Key Files

**To create:**
- `src/shared/strategies/__init__.py` — re-exports base classes and registry functions
- `src/shared/strategies/base.py` — `StrategyConfig`, `BaseStrategy` (ABC), `MarketSnapshot`, `Signal` dataclasses
- `src/shared/strategies/registry.py` — `discover_strategies()`, `get_strategy(id)`
- `src/shared/strategies/S1/__init__.py` — empty
- `src/shared/strategies/S1/config.py` — `S1Config(StrategyConfig)` with M3 spike reversion parameters
- `src/shared/strategies/S1/strategy.py` — `S1Strategy(BaseStrategy)` with `evaluate(snapshot) -> Signal | None`

**Key existing files (read-only reference):**
- `src/trading/strategies.py` — current Signal dataclass (lines 23-33) defines the fields the executor expects: `direction`, `strategy_name`, `entry_price`, `signal_data` (dict), `confidence_multiplier`, `created_at`, `locked_shares`, `locked_cost`, `locked_balance`, `locked_bet_size`
- `src/trading/executor.py` — imports `Signal` from `trading.strategies` (line 10); accesses `signal.direction`, `signal.entry_price`, `signal.locked_shares`, `signal.locked_cost`, `signal.signal_data` (dict keys: `bet_cost`, `price_min`, `price_max`, `stop_loss_price`, `shares`, `actual_cost`, `current_balance`, `bet_size`, `balance_at_signal`, `profitability_thesis`), `signal.strategy_name`, `signal.created_at`, `signal.confidence_multiplier`
- `src/trading/constants.py` — M3_CONFIG dict with all spike reversion parameters
- `src/analysis/backtest/module_3_mean_reversion.py` — analysis M3 logic operating on numpy arrays: `_find_spike()`, `_find_reversion()`, `run_single_config()`
- `src/analysis/backtest/data_loader.py` — produces dict with `ticks` (numpy array indexed by elapsed second), `total_seconds`, `market_id`, `market_type`, `asset`, `final_outcome`, `hour`
- `src/analysis/backtest/engine.py` — `Trade` dataclass and `make_trade()` function (analysis result format, separate from Signal)

### Data Model Design

**MarketSnapshot** (wraps what `data_loader.py` already produces):
```python
@dataclass
class MarketSnapshot:
    market_id: str
    market_type: str
    prices: np.ndarray        # up_price indexed by elapsed second, NaN for missing
    total_seconds: int        # market duration
    elapsed_seconds: float    # current elapsed time (for live: how far into market we are)
    metadata: dict             # asset, hour, started_at, etc.
```

**Signal** (superset of current trading Signal — D006):
```python
@dataclass
class Signal:
    direction: str             # 'Up' or 'Down'
    strategy_name: str         # e.g. 'S1_spike_reversion'
    entry_price: float
    signal_data: dict[str, Any] = field(default_factory=dict)
    confidence_multiplier: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Execution fields — populated by adapter, not strategy
    locked_shares: int = 0
    locked_cost: float = 0.0
    locked_balance: float = 0.0
    locked_bet_size: float = 0.0
```

The `locked_*` fields and `signal_data` dict are **execution-layer concerns** — the strategy's evaluate() only sets `direction`, `strategy_name`, `entry_price`, and strategy-specific `signal_data` keys. The trading adapter (S03) populates bet sizing fields before passing to the executor.

**StrategyConfig** (base for per-strategy config):
```python
@dataclass
class StrategyConfig:
    strategy_id: str          # 'S1', 'S2', etc.
    strategy_name: str        # 'S1_spike_reversion'
    enabled: bool = True
    # Subclasses add strategy-specific params
```

**BaseStrategy** (abstract):
```python
class BaseStrategy(ABC):
    config: StrategyConfig
    
    def __init__(self, config: StrategyConfig):
        self.config = config
    
    @abstractmethod
    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Pure signal detection — no side effects, no async, no DB."""
        ...
```

### S1 Strategy Logic (ported from analysis M3)

Port `_find_spike()` and `_find_reversion()` from `module_3_mean_reversion.py` — they already operate on numpy arrays. The trading version's logic is similar but uses tick indices on `list[Tick]` objects. The analysis version is the correct reference because it uses proper elapsed-second indexing.

S1Config holds the parameters from `trading/constants.py` M3_CONFIG: `spike_detection_window_seconds` (15), `spike_threshold_up` (0.80), `spike_threshold_down` (0.20), `reversion_reversal_pct` (0.10), `min_reversion_ticks` (10), `entry_price_threshold` (0.35). These are ported as-is per D005.

### Registry Design

```python
def discover_strategies() -> dict[str, type[BaseStrategy]]:
    """Scan shared/strategies/*/strategy.py for BaseStrategy subclasses."""

def get_strategy(strategy_id: str) -> BaseStrategy:
    """Instantiate and return a strategy by ID (e.g. 'S1')."""
```

Use `importlib` to dynamically import `shared.strategies.{id}.strategy` and find the `BaseStrategy` subclass. Each strategy module exports exactly one subclass. The registry scans subdirectories of `shared/strategies/` that contain a `strategy.py`.

### Build Order

1. **`base.py`** — Define all four dataclasses (`StrategyConfig`, `MarketSnapshot`, `Signal`, and `BaseStrategy` ABC). This is the foundation everything depends on. Verify: importable, no external deps beyond numpy + stdlib.

2. **`S1/config.py` + `S1/strategy.py`** — Port M3 spike reversion using the base classes. The evaluate() function takes MarketSnapshot and returns Signal | None. Verify: can instantiate S1Strategy, call evaluate() with a synthetic MarketSnapshot, get correct Signal or None.

3. **`registry.py`** — Dynamic discovery. Verify: `discover_strategies()` finds S1, `get_strategy('S1')` returns an S1Strategy instance.

4. **`__init__.py` files** — Re-export public API from `shared/strategies/__init__.py`.

### Verification Approach

All verification is unit-level (no DB, no network):

```bash
# 1. Import check — everything importable
python -c "from shared.strategies import BaseStrategy, StrategyConfig, MarketSnapshot, Signal"
python -c "from shared.strategies import discover_strategies, get_strategy"

# 2. Strategy evaluation — synthetic data
python -c "
from shared.strategies import get_strategy
import numpy as np
s = get_strategy('S1')
# Create a MarketSnapshot with a spike pattern
prices = np.full(300, 0.50)
prices[5:10] = 0.85  # spike up
prices[20:] = 0.72   # reversion
from shared.strategies.base import MarketSnapshot
snap = MarketSnapshot(market_id='test', market_type='btc_5m', prices=prices, total_seconds=300, elapsed_seconds=25.0, metadata={'asset': 'btc'})
result = s.evaluate(snap)
assert result is not None
assert result.direction == 'Down'  # contrarian to up-spike
print('S1 evaluate: PASS')
"

# 3. Registry discovery
python -c "
from shared.strategies.registry import discover_strategies
strategies = discover_strategies()
assert 'S1' in strategies
print(f'Found strategies: {list(strategies.keys())}')
"
```

## Constraints

- **Synchronous only** (D001) — evaluate() must not use `await`. Trading calls it from async context via trivial sync-in-async pattern.
- **No service-specific imports** — shared strategies cannot import from `trading.*`, `analysis.*`, or `core.*`. Only stdlib + numpy.
- **Signal superset** (D006) — Signal must include every field that `trading/executor.py` reads. The executor accesses: `signal.direction`, `signal.strategy_name`, `signal.entry_price`, `signal.signal_data`, `signal.confidence_multiplier`, `signal.created_at`, `signal.locked_shares`, `signal.locked_cost`, `signal.locked_balance`, `signal.locked_bet_size`.
- **Elapsed seconds time axis** (D002) — MarketSnapshot.prices indexed by elapsed second, matching analysis data_loader format.
- **numpy arrays** (D004) — prices as `np.ndarray`, not lists.
- **PYTHONPATH** — the project runs with `src/` on the Python path (imports like `from shared.config import ...`, `from trading.strategies import ...`). New code follows the same pattern: `from shared.strategies.base import ...`.

## Common Pitfalls

- **Strategy evaluate() doing execution work** — The trading M3/M4 functions mix signal detection with balance checking, bet sizing, DB queries (`already_traded_this_market`), and async calls. The shared evaluate() must be PURE signal detection only. Balance/sizing/dedup are adapter concerns (S03).
- **Signal.signal_data keys divergence** — The executor reads specific keys from `signal.signal_data` (`price_min`, `price_max`, `stop_loss_price`, `shares`, `actual_cost`, `bet_size`, `current_balance`, `balance_at_signal`, `profitability_thesis`). The strategy sets strategy-specific keys; the trading adapter must merge execution keys. Document which keys the strategy sets vs which the adapter sets.
- **NaN handling in numpy arrays** — The data_loader produces numpy arrays with NaN for missing seconds. The analysis M3 already handles this (`valid_mask = ~np.isnan(window)`). The ported S1 must preserve this pattern.

## Requirements Targeted

| Req | Role | How This Slice Delivers |
|-----|------|------------------------|
| R001 | Primary owner | Creates the single-definition framework: one config + one evaluate per strategy |
| R002 | Primary owner | Establishes `shared/strategies/S1/` folder structure with config.py + strategy.py |
| R003 | Primary owner | Defines MarketSnapshot with elapsed-seconds-indexed numpy array |
| R004 | Primary owner | Defines shared Signal dataclass with direction, entry_price, strategy_id, metadata |
| R008 | Primary owner | Implements registry that discovers strategies by scanning `shared/strategies/*/` |
