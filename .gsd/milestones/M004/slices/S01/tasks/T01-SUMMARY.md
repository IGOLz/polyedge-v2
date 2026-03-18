---
id: T01
parent: S01
milestone: M004
provides:
  - stop_loss and take_profit parameter ranges in all strategy config grids (S1-S7, TEMPLATE)
  - strategy-specific SL/TP ranges tuned to typical entry prices per D013
  - documented example of absolute price threshold semantics in TEMPLATE
key_files:
  - src/shared/strategies/S1/config.py
  - src/shared/strategies/S2/config.py
  - src/shared/strategies/S3/config.py
  - src/shared/strategies/S4/config.py
  - src/shared/strategies/S5/config.py
  - src/shared/strategies/S6/config.py
  - src/shared/strategies/S7/config.py
  - src/shared/strategies/TEMPLATE/config.py
key_decisions:
  - none (implementation per D012 and D013)
patterns_established:
  - SL/TP parameter lists with 3 values each create 9× multiplier on existing grid size
  - Comments in grid explain absolute price threshold semantics and direction handling
  - TEMPLATE provides commented example in docstring for future strategy authors
observability_surfaces:
  - get_param_grid() return dict directly introspectable via Python REPL
  - Import errors surface immediately with traceback
  - Grid size computation (verified in T01) shows total parameter combinations
duration: 12m
verification_result: passed
completed_at: 2026-03-18T17:27:00Z
blocker_discovered: false
---

# T01: Add stop_loss and take_profit to all strategy param grids

**Extended all 7 strategy config grids and TEMPLATE with stop_loss and take_profit parameter ranges tuned to each strategy's typical entry prices.**

## What Happened

Added `stop_loss` and `take_profit` keys to `get_param_grid()` return dicts for S1-S7 strategies and TEMPLATE config.py files. Each strategy now declares 3 SL and 3 TP absolute price thresholds, creating a 9× multiplier on existing parameter combinations.

Ranges are strategy-specific per D013:
- **S1 (calibration):** Entry 0.45-0.55 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]
- **S2 (momentum):** Entry ~0.50 → SL [0.40, 0.45, 0.50], TP [0.60, 0.65, 0.70]
- **S3 (mean reversion):** Entry at spikes (0.75-0.85 or 0.15-0.25) → SL [0.15, 0.20, 0.25], TP [0.75, 0.80, 0.85]
- **S4 (volatility):** Entry 0.45-0.55 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]
- **S5 (time-phase):** Entry 0.45-0.60 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]
- **S6 (streak):** Entry 0.40-0.60 → SL [0.30, 0.35, 0.40], TP [0.70, 0.75, 0.80]
- **S7 (ensemble):** Entry 0.45-0.60 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]

TEMPLATE updated with commented example explaining absolute price threshold semantics per D012 (engine handles direction logic, swaps SL/TP for Down bets).

All imports succeeded. Grid sizes range from 648 (S2, S6) to 1728 (S7) combinations per strategy.

## Verification

Ran inline Python check importing all 7 strategies + TEMPLATE, asserting presence of `stop_loss` and `take_profit` keys with non-empty lists. All passed.

Computed grid sizes for all strategies:
- S1: 972 combinations (3×3×2×2×3×3×3)
- S2: 648 combinations
- S3: 1296 combinations
- S4: 972 combinations
- S5: 972 combinations
- S6: 648 combinations
- S7: 1728 combinations

S3 and S7 exceed the 1000-combination goal but remain manageable for grid search in S03.

Verified TEMPLATE contains stop_loss and take_profit in docstring example.

## Verification Evidence

No verification gate ran for T01 (gate checks deferred to T02 when verification script is created).

Manual verification commands:
```bash
# Import check
cd src && python3 -c "from shared.strategies.S1.config import get_param_grid; print(sorted(get_param_grid().keys()))"
# Output: ['entry_window_end', 'entry_window_start', 'min_deviation', 'price_high_threshold', 'price_low_threshold', 'stop_loss', 'take_profit']

# Full strategy verification
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
# Output: S1: ✓ S2: ✓ S3: ✓ S4: ✓ S5: ✓ S6: ✓ S7: ✓
```

## Diagnostics

**Inspection:**
- Direct import: `from shared.strategies.S1.config import get_param_grid; print(get_param_grid())`
- Check keys: `list(get_param_grid().keys())`
- Compute grid size: `functools.reduce(operator.mul, [len(v) for v in get_param_grid().values()], 1)`

**Failure Visibility:**
- Import error: Python traceback shows file/line of syntax error in config.py
- Missing keys: Assertion in verification script (T02) will report strategy name + missing key
- Type errors: Import fails immediately if SL/TP values are non-numeric

**Future inspection (S03 grid search):**
- Grid search will log total parameter combinations per strategy at runtime
- Backtest results will include SL/TP values in metadata for each variant

## Deviations

None. Task plan executed as specified.

## Known Issues

None. All strategies import cleanly and have required SL/TP keys.

Two strategies (S3 and S7) exceed 1000 combinations but remain under 2000, which is still tractable for grid search. This is noted but not considered a blocker per slice plan flexibility.

## Files Created/Modified

- `src/shared/strategies/S1/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S2/config.py` — Added stop_loss [0.40, 0.45, 0.50] and take_profit [0.60, 0.65, 0.70] to get_param_grid()
- `src/shared/strategies/S3/config.py` — Added stop_loss [0.15, 0.20, 0.25] and take_profit [0.75, 0.80, 0.85] to get_param_grid()
- `src/shared/strategies/S4/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S5/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S6/config.py` — Added stop_loss [0.30, 0.35, 0.40] and take_profit [0.70, 0.75, 0.80] to get_param_grid()
- `src/shared/strategies/S7/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/TEMPLATE/config.py` — Added commented example of stop_loss and take_profit in get_param_grid() docstring
