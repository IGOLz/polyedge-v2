# S01: Parameter Grid Foundation

**Goal:** All 7 strategies (S1-S7) and TEMPLATE declare stop loss and take profit parameter ranges in their `get_param_grid()` return values.

**Demo:** Run verification script showing all strategies have `stop_loss` and `take_profit` keys with non-empty value lists; grid sizes confirm parameter space is manageable (<1000 combinations per strategy).

## Must-Haves

- S1-S7 `config.py` files have `stop_loss` and `take_profit` keys in `get_param_grid()` return dict
- SL/TP ranges are strategy-specific per D013, tuned to each strategy's typical entry prices
- TEMPLATE/config.py demonstrates SL/TP pattern with clear comments explaining absolute price threshold semantics
- Verification script imports all strategies, checks for SL/TP keys, prints grid sizes
- All checks pass: keys present, values non-empty, grid sizes reasonable

## Observability / Diagnostics

**Runtime Signals:**
- Import errors surface immediately via Python traceback showing file/line where config.py fails to load
- `get_param_grid()` return dict is introspectable via Python REPL or verification script
- Grid size computation (Cartesian product) reveals parameter space explosion if ranges misconfigured

**Inspection Surfaces:**
- Direct: `from shared.strategies.S1.config import get_param_grid; print(get_param_grid())`
- Verification script: `scripts/verify_m004_s01.py` prints per-strategy grid sizes and key presence
- Future grid search (S03): Will log total param combinations per strategy at runtime

**Failure Visibility:**
- Missing SL/TP keys: Verification script assertion fails with clear message (e.g., "S3 missing stop_loss")
- Empty parameter lists: Verification script catches `len(grid['stop_loss']) == 0`
- Type errors: Python import fails if config.py syntax broken
- Grid explosion: Verification script prints warning if any strategy >1000 combinations

**Redaction Constraints:**
- None — parameter ranges are strategic metadata but not sensitive

## Verification

- Command: `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py`
- Expected: All 7 strategies pass checks for SL/TP key presence and non-empty value lists
- Expected: Grid sizes printed showing <1000 combinations per strategy
- Expected: TEMPLATE has example SL/TP keys with comments
- **Diagnostic check:** Introduce syntax error in S1/config.py → verification script fails with traceback pointing to S1
- **Failure-path check:** Comment out 'stop_loss' key in S2/config.py → verification prints "S2 missing stop_loss" and exits non-zero

## Tasks

- [x] **T01: Add stop_loss and take_profit to all strategy param grids** `est:45m`
  - Why: Core deliverable — strategies must declare SL/TP ranges for grid search in S03
  - Files: `src/shared/strategies/S1/config.py`, `S2/config.py`, `S3/config.py`, `S4/config.py`, `S5/config.py`, `S6/config.py`, `S7/config.py`, `TEMPLATE/config.py`
  - Do: For each strategy, add `stop_loss` and `take_profit` keys to `get_param_grid()` return dict with 3 values each; tune ranges to strategy's entry prices per research guidance; update TEMPLATE with commented example
  - Verify: Import each config and call `get_param_grid()` — check return dict has both keys
  - Done when: All 8 config files modified, imports succeed, SL/TP keys present in all grids

- [x] **T02: Write and run verification script** `est:20m`
  - Why: Prove S01 complete — all strategies have SL/TP, grid sizes are manageable
  - Files: `src/scripts/verify_m004_s01.py`
  - Do: Write script that imports S1-S7 configs, calls `get_param_grid()`, checks for 'stop_loss' and 'take_profit' keys, verifies non-empty lists, computes and prints grid sizes (Cartesian product of all param values)
  - Verify: Run `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py` — all checks pass
  - Done when: Script runs cleanly, prints PASS for all strategies, grid sizes shown and all <1000

## Files Likely Touched

- `src/shared/strategies/S1/config.py`
- `src/shared/strategies/S2/config.py`
- `src/shared/strategies/S3/config.py`
- `src/shared/strategies/S4/config.py`
- `src/shared/strategies/S5/config.py`
- `src/shared/strategies/S6/config.py`
- `src/shared/strategies/S7/config.py`
- `src/shared/strategies/TEMPLATE/config.py`
- `src/scripts/verify_m004_s01.py`
