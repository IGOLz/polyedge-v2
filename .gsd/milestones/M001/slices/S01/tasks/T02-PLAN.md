---
estimated_steps: 5
estimated_files: 4
---

# T02: Port S1 spike reversion strategy and write verification script

**Slice:** S01 — Shared strategy framework + data model
**Milestone:** M001

## Description

Port the spike reversion strategy (analysis M3) as the first concrete strategy in the shared framework, proving the base classes actually work. Then write a verification script that exercises the full contract: signal detection, no-signal case, NaN handling, Signal field completeness, and import isolation.

The strategy logic comes from `analysis/backtest/module_3_mean_reversion.py` which already operates on numpy arrays indexed by elapsed seconds — the same format as MarketSnapshot. The parameters come from `trading/constants.py` M3_CONFIG. The porting is a reshape, not a rewrite: extract `_find_spike()` and `_find_reversion()`, make them methods on S1Strategy, and have `evaluate()` orchestrate them.

**Key reference files** (read these for porting, do NOT import them):
- `src/analysis/backtest/module_3_mean_reversion.py` — the algorithm to port (`_find_spike`, `_find_reversion`, `run_single_config`)
- `src/trading/constants.py` — M3_CONFIG dict with parameter values
- `src/trading/executor.py` — Signal field access patterns (to verify compatibility)

## Steps

1. **Create `src/shared/strategies/S1/__init__.py`** — empty file (makes S1 a package).

2. **Create `src/shared/strategies/S1/config.py`** with S1Config and get_default_config():

   Read `src/trading/constants.py` to get M3_CONFIG parameter values. Create:

   ```python
   from shared.strategies.base import StrategyConfig
   from dataclasses import dataclass

   @dataclass
   class S1Config(StrategyConfig):
       # Spike detection
       spike_detection_window_seconds: int = 15
       spike_threshold_up: float = 0.80
       spike_threshold_down: float = 0.20
       # Reversion detection
       reversion_reversal_pct: float = 0.10
       min_reversion_ticks: int = 10
       # Entry
       entry_price_threshold: float = 0.35

   def get_default_config() -> S1Config:
       return S1Config(
           strategy_id="S1",
           strategy_name="S1_spike_reversion",
       )
   ```

   **Important:** Read the actual M3_CONFIG values from `src/trading/constants.py` — the values above are from research and may need adjustment. Use the real values.

3. **Create `src/shared/strategies/S1/strategy.py`** with S1Strategy:

   Read `src/analysis/backtest/module_3_mean_reversion.py` and port the logic:

   - `_find_spike(prices, config)` — scans `prices[0:spike_detection_window_seconds]` for values above `spike_threshold_up` (spike up) or below `spike_threshold_down` (spike down). Must handle NaN via `~np.isnan()` masking. Returns the spike direction ('Up'/'Down') and spike details, or None.
   - `_find_reversion(prices, spike_direction, config)` — after a spike, looks for price reversal. For an up-spike, looks for price dropping by `reversion_reversal_pct` from peak. Returns the reversion point details or None.
   - `evaluate(snapshot: MarketSnapshot) -> Signal | None` — orchestrates: find spike → if spike found, find reversion → if reversion found and entry price below threshold, return Signal with direction opposite to spike (contrarian), else None.

   The strategy sets these `signal_data` keys (strategy-specific detection data):
   - `spike_direction`, `spike_max_price` or `spike_min_price`, `reversion_price`, `reversion_second`

   The `locked_*` fields and execution signal_data keys (`bet_cost`, `shares`, `actual_cost`, `current_balance`, `bet_size`, `balance_at_signal`) are NOT set by the strategy — they default to zero/empty and will be filled by the trading adapter in S03.

   **NaN handling pattern** from the analysis code:
   ```python
   window = prices[start:end]
   valid_mask = ~np.isnan(window)
   if not np.any(valid_mask):
       return None
   valid_prices = window[valid_mask]
   ```

4. **Create `src/scripts/verify_s01.py`** — standalone verification script:

   ```python
   """S01 verification — run from src/ directory."""
   import sys
   import numpy as np

   def check(name, condition):
       status = "PASS" if condition else "FAIL"
       print(f"  [{status}] {name}")
       if not condition:
           sys.exit(1)

   print("=== S01 Verification ===\n")

   # 1. Import check
   print("1. Imports")
   from shared.strategies import (BaseStrategy, StrategyConfig, MarketSnapshot,
                                   Signal, discover_strategies, get_strategy)
   check("All public API importable", True)

   # 2. Registry discovers S1
   print("\n2. Registry")
   strategies = discover_strategies()
   check("discover_strategies() finds S1", "S1" in strategies)
   s1 = get_strategy("S1")
   check("get_strategy('S1') returns instance", isinstance(s1, BaseStrategy))
   check("S1 config.strategy_id == 'S1'", s1.config.strategy_id == "S1")
   check("S1 config.strategy_name == 'S1_spike_reversion'", s1.config.strategy_name == "S1_spike_reversion")

   # 3. Spike-up → Down signal (contrarian)
   print("\n3. Spike detection — up spike")
   prices = np.full(300, 0.50)
   prices[3:8] = 0.85       # spike up in detection window
   prices[20:30] = 0.72     # partial reversion
   snap = MarketSnapshot(
       market_id="test_up", market_type="btc_5m",
       prices=prices, total_seconds=300,
       elapsed_seconds=30.0, metadata={"asset": "btc"}
   )
   result = s1.evaluate(snap)
   check("Returns a Signal (not None)", result is not None)
   if result:
       check("Direction is 'Down' (contrarian to up-spike)", result.direction == "Down")
       check("strategy_name set", result.strategy_name == "S1_spike_reversion")
       check("entry_price is a float", isinstance(result.entry_price, (int, float)))

   # 4. No spike → None
   print("\n4. No spike — flat prices")
   flat_prices = np.full(300, 0.50)
   snap_flat = MarketSnapshot(
       market_id="test_flat", market_type="btc_5m",
       prices=flat_prices, total_seconds=300,
       elapsed_seconds=30.0, metadata={"asset": "btc"}
   )
   result_flat = s1.evaluate(snap_flat)
   check("Returns None for flat prices", result_flat is None)

   # 5. NaN resilience
   print("\n5. NaN handling")
   nan_prices = np.full(300, np.nan)
   snap_nan = MarketSnapshot(
       market_id="test_nan", market_type="btc_5m",
       prices=nan_prices, total_seconds=300,
       elapsed_seconds=30.0, metadata={"asset": "btc"}
   )
   result_nan = s1.evaluate(snap_nan)
   check("All-NaN returns None (no crash)", result_nan is None)

   # 6. Signal field completeness (D006)
   print("\n6. Signal backward compatibility")
   sig = Signal(direction="Up", strategy_name="test", entry_price=0.5)
   check("signal.locked_shares defaults to 0", sig.locked_shares == 0)
   check("signal.locked_cost defaults to 0.0", sig.locked_cost == 0.0)
   check("signal.locked_balance defaults to 0.0", sig.locked_balance == 0.0)
   check("signal.locked_bet_size defaults to 0.0", sig.locked_bet_size == 0.0)
   check("signal.signal_data defaults to {}", sig.signal_data == {})
   check("signal.confidence_multiplier defaults to 1.0", sig.confidence_multiplier == 1.0)
   check("signal.created_at is set", sig.created_at is not None)

   # 7. Import isolation — no forbidden imports
   print("\n7. Import isolation")
   import ast, pathlib
   strategies_dir = pathlib.Path(__file__).parent.parent / "shared" / "strategies"
   forbidden = []
   for py_file in strategies_dir.rglob("*.py"):
       tree = ast.parse(py_file.read_text())
       for node in ast.walk(tree):
           if isinstance(node, (ast.Import, ast.ImportFrom)):
               module = getattr(node, 'module', '') or ''
               names = [a.name for a in node.names] if isinstance(node, ast.Import) else [module]
               for name in names:
                   if name and any(name.startswith(p) for p in ('trading', 'analysis', 'core')):
                       forbidden.append(f"{py_file.name}: {name}")
   check(f"No forbidden imports (found: {forbidden})", len(forbidden) == 0)

   print("\n=== All S01 checks passed ===")
   ```

   Adapt the test data if the actual M3 algorithm has different thresholds — the spike values (0.85) must exceed `spike_threshold_up`, and the reversion must show enough price movement. Read the actual constants to calibrate.

5. **Run verification:**
   ```bash
   cd src && python scripts/verify_s01.py
   ```
   All checks must pass. If any fail, fix the strategy code until they pass.

## Must-Haves

- [ ] `S1/config.py` has S1Config with all M3_CONFIG parameters and `get_default_config()` function
- [ ] `S1/strategy.py` has S1Strategy(BaseStrategy) with `evaluate()` that detects spikes and reversions
- [ ] evaluate() handles NaN values without crashing
- [ ] evaluate() returns Signal with direction opposite to spike (contrarian)
- [ ] evaluate() returns None when no spike detected
- [ ] `scripts/verify_s01.py` passes all 7 check groups
- [ ] No imports from `trading.*`, `analysis.*`, or `core.*` in any `shared/strategies/` file

## Verification

- `cd src && python scripts/verify_s01.py` — all checks pass (exit code 0)
- `cd src && python -c "from shared.strategies import get_strategy; s = get_strategy('S1'); print(s.config.strategy_name)"` prints `S1_spike_reversion`

## Inputs

- `src/shared/strategies/base.py` — StrategyConfig, BaseStrategy, MarketSnapshot, Signal from T01
- `src/shared/strategies/registry.py` — discover_strategies, get_strategy from T01
- `src/analysis/backtest/module_3_mean_reversion.py` — algorithm logic to port (READ ONLY, do not import)
- `src/trading/constants.py` — M3_CONFIG parameter values (READ ONLY, copy values)
- `src/trading/executor.py` — Signal field usage reference (READ ONLY)

## Observability Impact

- **New signal surface:** `S1Strategy.evaluate()` returns a `Signal` with `signal_data` keys (`spike_direction`, `spike_max_price`/`spike_min_price`, `reversion_price`, `reversion_second`) that downstream adapters can log or persist for trade diagnostics.
- **Inspection:** `get_strategy('S1').config` exposes all tunable parameters; `dataclasses.fields(S1Config)` provides introspectable schema for config validation.
- **Failure visibility:** `evaluate()` returns `None` for any no-signal condition (no spike, no reversion, price above threshold, NaN data) — there is no exception path to catch. Callers distinguish "no signal" from "error" by the `None` return.
- **Verification script:** `src/scripts/verify_s01.py` exercises all 7 check groups (imports, registry, spike detection, flat prices, NaN handling, signal defaults, import isolation) and exits non-zero on any failure.

## Expected Output

- `src/shared/strategies/S1/__init__.py` — empty package init
- `src/shared/strategies/S1/config.py` — S1Config dataclass + get_default_config()
- `src/shared/strategies/S1/strategy.py` — S1Strategy with evaluate(), _find_spike(), _find_reversion()
- `src/scripts/verify_s01.py` — verification script, all checks passing
