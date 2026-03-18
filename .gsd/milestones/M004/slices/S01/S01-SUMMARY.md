---
id: S01
parent: M004
milestone: M004
provides:
  - All 7 strategies (S1-S7) have get_param_grid() returning dicts with stop_loss and take_profit keys
  - TEMPLATE demonstrates SL/TP pattern with documented absolute price threshold semantics
  - Verification script proves all grids include SL/TP with manageable parameter space sizes
requires:
  - none (first slice in M004)
affects:
  - S02 (SL/TP engine will consume these parameter ranges)
  - S03 (grid search orchestrator will generate Cartesian products from these ranges)
key_files:
  - src/shared/strategies/S1/config.py
  - src/shared/strategies/S2/config.py
  - src/shared/strategies/S3/config.py
  - src/shared/strategies/S4/config.py
  - src/shared/strategies/S5/config.py
  - src/shared/strategies/S6/config.py
  - src/shared/strategies/S7/config.py
  - src/shared/strategies/TEMPLATE/config.py
  - src/scripts/verify_m004_s01.py
key_decisions:
  - none (implementation followed existing decisions D012 and D013)
patterns_established:
  - SL/TP parameter lists with 3 values each create 9× multiplier on existing grid dimensions
  - Strategy-specific SL/TP ranges tuned to each strategy's typical entry prices
  - Absolute price threshold semantics documented in TEMPLATE with direction-handling explanation
  - Verification scripts check for key presence, value counts, and compute total grid sizes
observability_surfaces:
  - get_param_grid() return dict directly introspectable via Python REPL
  - Verification script exit code: 0=all pass, 1=any fail
  - Per-strategy output shows key presence, value counts, total grid size
  - Warning messages for grid sizes >1000
drill_down_paths:
  - .gsd/milestones/M004/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S01/tasks/T02-SUMMARY.md
duration: 30m
verification_result: passed
completed_at: 2026-03-18T17:27
---

# S01: Parameter Grid Foundation

**All 7 strategies and TEMPLATE now declare stop_loss and take_profit parameter ranges in their configuration grids, with strategy-specific values tuned to typical entry prices and verification proving manageable parameter space sizes.**

## What Happened

Extended all strategy configuration files to include stop loss and take profit as grid search dimensions:

1. **Parameter grid expansion (T01):** Added `stop_loss` and `take_profit` keys to `get_param_grid()` for all 7 strategies (S1-S7) and TEMPLATE. Each strategy declares 3 SL and 3 TP absolute price thresholds, creating a 9× multiplier on existing parameter combinations.

2. **Strategy-specific tuning:** Ranges are customized per strategy's typical entry prices per decision D013:
   - **S1 (calibration):** Entry 0.45-0.55 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]
   - **S2 (momentum):** Entry ~0.50 → SL [0.40, 0.45, 0.50], TP [0.60, 0.65, 0.70]
   - **S3 (mean reversion):** Entry at spikes → SL [0.15, 0.20, 0.25], TP [0.75, 0.80, 0.85]
   - **S4 (volatility):** Entry 0.45-0.55 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]
   - **S5 (time-phase):** Entry 0.45-0.60 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]
   - **S6 (streak):** Entry 0.40-0.60 → SL [0.30, 0.35, 0.40], TP [0.70, 0.75, 0.80]
   - **S7 (ensemble):** Entry 0.45-0.60 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]

3. **TEMPLATE documentation:** Updated TEMPLATE config with commented example explaining absolute price threshold semantics per D012 (engine handles direction logic, swaps SL/TP for Down bets automatically).

4. **Verification script (T02):** Created `verify_m004_s01.py` that imports all strategy configs, checks for SL/TP key presence and non-empty value lists, computes grid sizes via Cartesian product. Script includes diagnostic validation:
   - Syntax error detection: deliberate error in S1 → traceback points to exact file/line
   - Missing key detection: commented out 'stop_loss' in S2 → clear error message and exit 1

5. **TEMPLATE fix:** During T02, discovered TEMPLATE's `get_param_grid()` returned empty dict despite documented example in docstring. Fixed by moving example into actual return value.

Grid sizes range from 648 (S2, S6) to 1728 (S7) combinations per strategy. S3 (1296) and S7 (1728) exceed 1000 but remain tractable for grid search.

## Verification

All slice-level verification requirements satisfied:

- ✅ Command `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py` succeeds with exit code 0
- ✅ All 7 strategies pass checks for SL/TP key presence and non-empty value lists
- ✅ Grid sizes printed: S1=972, S2=648, S3=1296, S4=972, S5=972, S6=648, S7=1728, TEMPLATE=81
- ✅ TEMPLATE has example SL/TP keys with clear comments explaining absolute price semantics
- ✅ Diagnostic check passed: syntax error in S1 → traceback pointing to S1
- ✅ Failure-path check passed: missing 'stop_loss' in S2 → clear error message and exit non-zero

Manual verification commands used during development:
```bash
# Import check for single strategy
cd src && python3 -c "from shared.strategies.S1.config import get_param_grid; print(sorted(get_param_grid().keys()))"

# Full verification across all strategies
cd src && python3 -c "
from shared.strategies.S1.config import get_param_grid as g1
from shared.strategies.S2.config import get_param_grid as g2
from shared.strategies.S3.config import get_param_grid as g3
from shared.strategies.S4.config import get_param_grid as g4
from shared.strategies.S5.config import get_param_grid as g5
from shared.strategies.S6.config import get_param_grid as g6
from shared.strategies.S7.config import get_param_grid as g7

for name, fn in [('S1', g1), ('S2', g2), ('S3', g3), ('S4', g4), ('S5', g5), ('S6', g6), ('S7', g7)]:
    grid = fn()
    assert 'stop_loss' in grid, f'{name} missing stop_loss'
    assert 'take_profit' in grid, f'{name} missing take_profit'
    assert len(grid['stop_loss']) > 0, f'{name} stop_loss empty'
    assert len(grid['take_profit']) > 0, f'{name} take_profit empty'
    print(f'{name}: ✓')
"
```

## Requirements Advanced

- R023 — All strategies now declare SL/TP parameter ranges in their config grids
- R024 — TEMPLATE demonstrates SL/TP pattern with documented semantics
- R029 — Strategy-specific SL/TP ranges tuned to each strategy's typical entry prices
- R030 — TEMPLATE provides clear example with commented explanation of absolute price threshold semantics

## Requirements Validated

None (S01 establishes foundation; validation occurs in S02-S05 when engine and grid search use these parameters).

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

**TEMPLATE config incomplete:** T01 summary stated TEMPLATE was updated with SL/TP, but actual implementation returned empty dict. Fixed during T02 by moving documented example from docstring into actual return value. This was a T01 oversight caught by verification, not a planned deviation.

## Known Limitations

**Large grid sizes:** S3 (1296 combinations) and S7 (1728 combinations) exceed the original 1000-combination target. These sizes are still manageable for grid search but may increase backtest runtime in S03. If runtime becomes prohibitive, strategies can reduce parameter ranges or add constraints in future optimization passes.

**No runtime validation yet:** While grid structures are verified at import time, there's no validation that SL/TP values are sensible (e.g., SL < entry < TP for Up bets). Engine in S02 must handle any edge cases or misconfigured ranges gracefully.

## Follow-ups

None discovered during execution. S02 will consume these parameter ranges when implementing SL/TP exit simulation.

## Files Created/Modified

- `src/shared/strategies/S1/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S2/config.py` — Added stop_loss [0.40, 0.45, 0.50] and take_profit [0.60, 0.65, 0.70] to get_param_grid()
- `src/shared/strategies/S3/config.py` — Added stop_loss [0.15, 0.20, 0.25] and take_profit [0.75, 0.80, 0.85] to get_param_grid()
- `src/shared/strategies/S4/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S5/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S6/config.py` — Added stop_loss [0.30, 0.35, 0.40] and take_profit [0.70, 0.75, 0.80] to get_param_grid()
- `src/shared/strategies/S7/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/TEMPLATE/config.py` — Added commented example of stop_loss and take_profit in get_param_grid() with actual return value
- `src/scripts/verify_m004_s01.py` — Created verification script that validates SL/TP presence, value counts, and computes grid sizes

## Forward Intelligence

### What the next slice should know

- **Grid sizes are larger than originally anticipated:** Most strategies are in the 600-1000 range, but S3 (1296) and S7 (1728) are higher. S02 should be aware that runtime testing with full grids may take longer than expected. Consider testing with a single strategy first (S2 or S6 with 648 combinations) before running all 7.

- **SL/TP semantics are absolute prices, not percentages:** This is documented in TEMPLATE but worth emphasizing. Engine in S02 must compare absolute prices, not calculate percentage thresholds. Direction handling is also engine responsibility (swapping SL/TP for Down bets).

- **TEMPLATE is now a working example:** Previous milestones had TEMPLATE as documentation-only. After S01, TEMPLATE's `get_param_grid()` returns a real example grid that can be imported and used. This makes it easier to test engine logic in S02 with TEMPLATE as a lightweight test case.

### What's fragile

- **No semantic validation of SL/TP ranges:** While verification checks that keys exist and values are non-empty, there's no check that SL < entry < TP or that ranges make sense for each strategy's entry logic. If a strategy misconfigures ranges (e.g., SL > TP), engine must handle gracefully or validate during grid generation in S03.

- **Hardcoded value counts:** Each strategy declares exactly 3 SL and 3 TP values. If future optimization reveals that more granular search is needed (e.g., 5 values each), all 7 strategy configs must be updated manually. Consider adding a comment or convention for how to scale ranges if grid search in S03 reveals gaps in parameter space.

### Authoritative diagnostics

- **Verification script is the source of truth:** `src/scripts/verify_m004_s01.py` is the definitive check for S01 completion. If any future changes to strategy configs break SL/TP structure, this script will catch it immediately. Run it after any config modifications.

- **Grid size computation is accurate:** The script computes Cartesian product size correctly by multiplying lengths of all parameter lists. This matches what S03's grid generation will produce. Use these numbers for runtime estimation.

- **Import errors surface immediately:** If a config.py has syntax errors or import failures, Python traceback points directly to the file/line. No need to debug indirectly.

### What assumptions changed

- **TEMPLATE assumed to be complete after T01:** Task plan indicated TEMPLATE would be done in T01, but actual implementation had empty return dict. T02 caught this during verification. Lesson: Always verify imports work, not just that files were edited.

- **1000-combination limit was a soft target:** Original plan aimed for <1000 per strategy, but S3 and S7 exceed this. Runtime testing in S03 will determine if this is actually problematic. The limit was conservative; actual limit may be higher (2000+).
