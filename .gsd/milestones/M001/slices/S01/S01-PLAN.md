# S01: Shared strategy framework + data model

**Goal:** `shared/strategies/` exists with base classes (StrategyConfig, MarketSnapshot, Signal, BaseStrategy), a folder-based registry, and S1 (spike reversion) ported with config. Importable and unit-testable but not yet wired to analysis or trading.
**Demo:** `cd src && python -c "from shared.strategies import get_strategy; s = get_strategy('S1'); print(s.config.strategy_name)"` prints `S1_spike_reversion`.

## Must-Haves

- `StrategyConfig`, `BaseStrategy` (ABC), `MarketSnapshot`, `Signal` dataclasses defined in `shared/strategies/base.py`
- `Signal` includes all fields the trading executor reads: `direction`, `strategy_name`, `entry_price`, `signal_data` (dict), `confidence_multiplier`, `created_at`, `locked_shares`, `locked_cost`, `locked_balance`, `locked_bet_size` (D006)
- `MarketSnapshot.prices` is a numpy ndarray indexed by elapsed second (D002, D004)
- `BaseStrategy.evaluate(snapshot)` is synchronous, returns `Signal | None` (D001)
- `registry.py` discovers strategies by scanning `shared/strategies/*/strategy.py` for BaseStrategy subclasses
- S1 strategy ported from analysis M3 (`_find_spike`, `_find_reversion`) operating on numpy arrays with NaN handling
- S1Config holds parameters from trading `constants.py` M3_CONFIG (D005)
- No imports from `trading.*`, `analysis.*`, or `core.*` — only stdlib + numpy

## Proof Level

- This slice proves: contract
- Real runtime required: no
- Human/UAT required: no

## Verification

All verification runs from `src/` directory with `PYTHONPATH=.`:

- `cd src && python -c "from shared.strategies import BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy"` — all public API importable
- `cd src && python -c "from shared.strategies import get_strategy; s = get_strategy('S1'); assert s.config.strategy_id == 'S1'; assert s.config.strategy_name == 'S1_spike_reversion'; print('registry: PASS')"` — registry discovers S1
- `cd src && python scripts/verify_s01.py` — verification script that:
  1. Creates a MarketSnapshot with a spike-up pattern, asserts S1 returns a Down signal (contrarian)
  2. Creates a MarketSnapshot with no spike, asserts S1 returns None
  3. Creates a MarketSnapshot with NaN gaps, asserts no crash
  4. Verifies Signal has all executor-required fields with correct defaults
  5. Verifies no imports from trading/analysis/core in any shared/strategies file
- `cd src && python -c "from shared.strategies import get_strategy; got_error = False; exec(\"try:\\n    get_strategy('NONEXISTENT')\\nexcept KeyError as e:\\n    got_error = True\\n    assert 'Available' in str(e)\"); assert got_error; print('error_path: PASS')"` — get_strategy raises KeyError with available-strategy list for unknown IDs

## Observability / Diagnostics

### Runtime Signals
- **Registry discovery logging:** `discover_strategies()` silently skips broken modules (`except Exception: continue`). In debug scenarios, callers can inspect the returned dict to see which strategies loaded. No hidden state — `_registry` is module-level but always returned as a copy.
- **Strategy instantiation errors:** `get_strategy(id)` raises `KeyError` with available strategy IDs listed in the message, providing immediate diagnostic context.

### Inspection Surfaces
- `discover_strategies()` returns `dict[str, type[BaseStrategy]]` — inspectable mapping of what loaded.
- `get_strategy(id)` on unknown ID produces a structured error: `KeyError("Strategy 'X' not found. Available: ['S1', ...]")`.
- Signal dataclass fields are introspectable via `dataclasses.fields(Signal)` for schema validation.

### Failure Visibility
- Missing `strategy.py` in a strategy folder: silently skipped (folder exists but no strategy module). Visible by comparing folder listing vs `discover_strategies()` output.
- Broken strategy module (import error): silently skipped. Diagnosable by comparing expected vs actual registry keys.
- Missing `config.py` or `get_default_config()`: raises `ImportError`/`AttributeError` at `get_strategy()` call time with standard Python traceback.

### Redaction Constraints
- No secrets or PII in this slice. All data is market prices, strategy parameters, and signal metadata.

## Integration Closure

- Upstream surfaces consumed: parameter values from `trading/constants.py` M3_CONFIG (copied, not imported); algorithm logic from `analysis/backtest/module_3_mean_reversion.py` (ported, not imported)
- New wiring introduced in this slice: none — the package is importable but not yet consumed by analysis or trading
- What remains before the milestone is truly usable end-to-end: S02 (analysis adapter), S03 (trading adapter), S04 (parity verification), S05 (template + optimization)

## Tasks

- [x] **T01: Create base framework with dataclasses and registry** `est:30m`
  - Why: Establishes the type contracts (StrategyConfig, MarketSnapshot, Signal, BaseStrategy) and discovery mechanism that everything else depends on. Delivers R001 (single-definition framework), R003 (MarketSnapshot with elapsed-seconds prices), R004 (shared Signal type), R008 (registry).
  - Files: `src/shared/strategies/__init__.py`, `src/shared/strategies/base.py`, `src/shared/strategies/registry.py`
  - Do: Create `base.py` with four types exactly matching the research data model design. Signal must include all executor fields (D006) with execution fields defaulting to zero/empty. Create `registry.py` using importlib to scan `shared/strategies/*/strategy.py`. Create `__init__.py` re-exporting the public API. Constraints: synchronous only (D001), numpy arrays (D004), elapsed seconds (D002), no trading/analysis/core imports.
  - Verify: `cd src && python -c "from shared.strategies import BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy; print('imports: PASS')"`
  - Done when: All four types importable from `shared.strategies`, registry callable (returns empty dict since no strategies exist yet), Signal has all 10 executor-required fields.

- [x] **T02: Port S1 spike reversion strategy and write verification script** `est:45m`
  - Why: Proves the framework works end-to-end by implementing a real strategy. Delivers R002 (folder structure with config + evaluate) and validates R001/R003/R004/R008 with a working strategy.
  - Files: `src/shared/strategies/S1/__init__.py`, `src/shared/strategies/S1/config.py`, `src/shared/strategies/S1/strategy.py`, `src/scripts/verify_s01.py`
  - Do: Create `S1/config.py` with S1Config(StrategyConfig) holding M3 parameters from trading constants.py M3_CONFIG. Create `S1/strategy.py` with S1Strategy(BaseStrategy) porting `_find_spike()` and `_find_reversion()` from `analysis/backtest/module_3_mean_reversion.py`. The evaluate() method operates on `snapshot.prices` (numpy ndarray), handles NaN via `~np.isnan()` masking, and returns Signal with direction/strategy_name/entry_price/signal_data or None. Write `scripts/verify_s01.py` that tests spike detection, no-signal case, NaN resilience, Signal field completeness, and import isolation. Reference files for porting: `src/analysis/backtest/module_3_mean_reversion.py` (algorithm), `src/trading/constants.py` (M3_CONFIG params), `src/trading/executor.py` (Signal field usage).
  - Verify: `cd src && python scripts/verify_s01.py` — all checks pass. `cd src && python -c "from shared.strategies import get_strategy; s = get_strategy('S1'); print(s.config.strategy_name)"` prints `S1_spike_reversion`.
  - Done when: Registry discovers S1, evaluate() returns correct signals on synthetic data, verification script passes all 5 checks.

## Files Likely Touched

- `src/shared/strategies/__init__.py`
- `src/shared/strategies/base.py`
- `src/shared/strategies/registry.py`
- `src/shared/strategies/S1/__init__.py`
- `src/shared/strategies/S1/config.py`
- `src/shared/strategies/S1/strategy.py`
- `src/scripts/verify_s01.py`
