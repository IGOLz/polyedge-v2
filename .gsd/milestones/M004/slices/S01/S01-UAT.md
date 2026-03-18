---
id: S01-UAT
parent: S01
milestone: M004
written: 2026-03-18T17:27
---

# S01: Parameter Grid Foundation — UAT

**Milestone:** M004
**Written:** 2026-03-18T17:27

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: S01 deliverables are pure configuration artifacts (Python dicts returned by functions). No runtime services, user interfaces, or live data involved. Verification script provides deterministic validation of all requirements.

## Preconditions

- Working directory: `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004`
- Python 3 available with PYTHONPATH set to `src/`
- All strategy config files exist: `src/shared/strategies/S1-S7/config.py` and `src/shared/strategies/TEMPLATE/config.py`

## Smoke Test

Run verification script and confirm all strategies pass:
```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004/src && PYTHONPATH=. python3 scripts/verify_m004_s01.py
```
**Expected:** Exit code 0, final message "✓ All checks passed. S01 complete."

## Test Cases

### 1. All strategies have stop_loss and take_profit keys

1. Run verification script: `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py`
2. Check output for each strategy (S1-S7, TEMPLATE)
3. **Expected:** Each strategy shows:
   ```
   [PASS] {strategy} has stop_loss key
   [PASS] {strategy} has take_profit key
   ```

### 2. All SL/TP parameter lists are non-empty

1. Run verification script
2. Check output for value counts
3. **Expected:** Each strategy shows:
   ```
   [PASS] {strategy} stop_loss has 3 values
   [PASS] {strategy} take_profit has 3 values
   ```

### 3. Grid sizes are computed and reasonable

1. Run verification script
2. Check "Grid size: X combinations" for each strategy
3. **Expected:**
   - S1: 972 combinations
   - S2: 648 combinations
   - S3: 1296 combinations (with warning)
   - S4: 972 combinations
   - S5: 972 combinations
   - S6: 648 combinations
   - S7: 1728 combinations (with warning)
   - TEMPLATE: 81 combinations
4. **Expected:** S3 and S7 show `[WARN] Grid size exceeds 1000 — may be slow` but script still passes

### 4. Strategy-specific SL/TP ranges are tuned correctly

1. Inspect S1 config: `cd src && python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid()['stop_loss']); print(get_param_grid()['take_profit'])"`
2. **Expected:**
   - stop_loss: [0.35, 0.40, 0.45]
   - take_profit: [0.65, 0.70, 0.75]
3. Inspect S3 config (mean reversion): `cd src && python3 -c "from shared.strategies.S3.config import get_param_grid; print(get_param_grid()['stop_loss']); print(get_param_grid()['take_profit'])"`
4. **Expected:**
   - stop_loss: [0.15, 0.20, 0.25]
   - take_profit: [0.75, 0.80, 0.85]
   (Confirms S3 has wider ranges for spike-based entry strategy)

### 5. TEMPLATE has documented example

1. Inspect TEMPLATE config: `cd src && python3 -c "from shared.strategies.TEMPLATE.config import get_param_grid; grid = get_param_grid(); print('stop_loss' in grid, 'take_profit' in grid, len(grid['stop_loss']), len(grid['take_profit']))"`
2. **Expected:** Output shows `True True 3 3`
3. Read TEMPLATE comments: `cd src && grep -A5 "stop_loss\|take_profit" shared/strategies/TEMPLATE/config.py | head -20`
4. **Expected:** Comments explain absolute price threshold semantics and direction handling

### 6. All strategies import without errors

1. Run full import test: `cd src && python3 -c "from shared.strategies.S1.config import get_param_grid as g1; from shared.strategies.S2.config import get_param_grid as g2; from shared.strategies.S3.config import get_param_grid as g3; from shared.strategies.S4.config import get_param_grid as g4; from shared.strategies.S5.config import get_param_grid as g5; from shared.strategies.S6.config import get_param_grid as g6; from shared.strategies.S7.config import get_param_grid as g7; from shared.strategies.TEMPLATE.config import get_param_grid as gt; print('All imports succeeded')"`
2. **Expected:** Output shows "All imports succeeded" with no errors

## Edge Cases

### Syntax error in strategy config

1. Introduce syntax error in S1/config.py: `cd src && echo "syntax error" >> shared/strategies/S1/config.py`
2. Run verification script: `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py`
3. **Expected:** Python traceback points to S1/config.py with line number of syntax error
4. Revert change: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004 && git checkout src/shared/strategies/S1/config.py`

### Missing stop_loss key

1. Comment out 'stop_loss' in S2/config.py: Edit line to remove key from dict
2. Run verification script
3. **Expected:** Output shows `[FAIL] S2 missing 'stop_loss'` and script exits with code 1
4. Revert change

### Empty parameter list

1. Change S4 stop_loss to empty list: `'stop_loss': []`
2. Run verification script
3. **Expected:** Output shows `[FAIL] S4 stop_loss is empty` and script exits with code 1
4. Revert change

## Failure Signals

- Import errors: Python traceback with file/line of config.py that failed to load
- Missing keys: `[FAIL] {strategy} missing '{key}'` in verification output
- Empty parameter lists: `[FAIL] {strategy} {key} is empty` in verification output
- Verification script exits with non-zero code on any failure
- Strategy shows `[PASS]` for some checks but not others (indicates partial completion)

## Requirements Proved By This UAT

- R023 (core-capability): All strategies declare SL/TP parameter ranges — verified by test cases 1, 2, 6
- R024 (core-capability): TEMPLATE demonstrates SL/TP pattern — verified by test case 5
- R029 (core-capability): Strategy-specific SL/TP ranges tuned to entry prices — verified by test case 4
- R030 (operability): TEMPLATE has clear example with documented semantics — verified by test case 5

## Not Proven By This UAT

- **Correctness of SL/TP values:** UAT confirms ranges exist and are strategy-specific, but does not validate that chosen values are optimal or sensible. Runtime testing in S03 will reveal if ranges are too narrow/wide.
- **Engine SL/TP logic:** S01 only provides parameter ranges; S02 must prove engine correctly uses these values to exit trades early.
- **Grid search integration:** S03 will prove that these parameter ranges actually feed into Cartesian product generation correctly.
- **Backtest profitability:** S04/S05 will prove that SL/TP actually improves strategy performance.

## Notes for Tester

- **Grid size warnings are expected:** S3 and S7 trigger `[WARN] Grid size exceeds 1000` — this is informational, not a failure. Warnings confirm the monitoring works correctly.
- **TEMPLATE is now executable:** Unlike previous milestones where TEMPLATE was documentation-only, this TEMPLATE can be imported and run. Feel free to test with TEMPLATE as a lightweight validation target.
- **Edge case tests require git revert:** Diagnostic tests modify config files. Use `git checkout <file>` to restore clean state after each edge case test.
- **No live services needed:** All tests run against static config files with pure Python imports. No database, no servers, no network requests.
