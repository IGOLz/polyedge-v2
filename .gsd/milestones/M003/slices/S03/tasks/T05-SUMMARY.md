---
id: T05
parent: S03
milestone: M003
provides:
  - Comprehensive verification script (scripts/verify_s03_strategies.sh) that validates all 7 strategies (S1-S7) across 6 check groups
  - Slice-level health check for S03 implementation quality
  - Executable documentation of S03 strategy requirements
key_files:
  - scripts/verify_s03_strategies.sh
patterns_established:
  - "Embedded Python in bash verification scripts: Each check group uses python3 <<'PYEOF' ... PYEOF to avoid bash portability issues with complex logic"
  - "Structured verification output: Each check uses ✓/✗/○ symbols with clear pass/fail messages and detailed failure diagnostics"
  - "Synthetic market patterns for strategy testing: spike, flat, nan_heavy, extreme — tests strategies without requiring real market data"
observability_surfaces:
  - "Run `bash scripts/verify_s03_strategies.sh` to check all 7 strategies (exit 0 = pass, exit 1 = fail with detailed diagnostics)"
  - "Check output shows: which strategies failed which checks, parameter grid sizes, signal structure validation results, edge case handling"
duration: 15m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T05: Write comprehensive verification script covering all strategies

**Created comprehensive verification script that validates all 7 strategies across 6 check groups with 100% pass rate.**

## What Happened

Created `scripts/verify_s03_strategies.sh`, an executable bash script with embedded Python checks that serves as the canonical health check for S03. The script validates all 7 strategies (S1-S7) across 6 verification groups:

1. **Import checks** — All 7 strategies import without errors
2. **Instantiation checks** — All 7 instantiate with correct metadata (strategy_id, strategy_name)
3. **Parameter grid checks** — All 7 have meaningful grids (2+ parameters, 2+ values each, 72-192 combinations)
4. **Synthetic evaluation checks** — All 7 handle 4 market patterns (spike, flat, nan_heavy, extreme) without crashing
5. **Signal structure checks** — Signals have required fields (direction, entry_price, entry_second in signal_data) when returned
6. **Edge case checks** — All 7 return None gracefully for insufficient data (5 valid ticks in 300s window)

The script uses embedded Python (`python3 <<'PYEOF' ... PYEOF`) for complex checks to avoid bash portability issues. Each check group prints structured output with ✓/✗/○ symbols and exits with code 1 on first failure, code 0 if all checks pass.

All 6 check groups passed on first run. The script verified:
- All 7 strategies import and instantiate correctly
- Parameter grids range from 72 (S2, S6) to 192 (S7) combinations
- All strategies handle synthetic patterns without crashes
- S1 returned a valid signal on the test pattern; S2-S7 returned None (valid behavior for patterns that don't meet their detection thresholds)
- All strategies return None (not crash) for sparse data

## Verification

Ran the verification script itself to validate all 7 strategies:

```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003
bash scripts/verify_s03_strategies.sh
```

**Output summary:**
- Check 1: All 7 strategies imported successfully
- Check 2: All 7 instantiated with correct metadata
- Check 3: All 7 have valid parameter grids (72-192 combinations)
- Check 4: All 7 handled 4 synthetic patterns without crashing
- Check 5: All returned signals have correct structure (S1 triggered, S2-S7 returned None as expected)
- Check 6: All 7 handled sparse data gracefully (returned None, no crashes)

Exit code: 0 (all checks passed)

This script fulfills the slice-level verification requirement in the S03 plan: "Run verification script that proves all strategies import without errors, instantiate with correct config, have non-empty parameter grids, run evaluate() on synthetic market snapshots without crashing, return None or valid Signal objects, populate entry_second when returning signals."

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | bash scripts/verify_s03_strategies.sh | 0 | ✅ pass | ~2s |

## Diagnostics

**How to use this script:**
```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003
bash scripts/verify_s03_strategies.sh
```

**Exit codes:**
- 0: All checks passed
- 1: At least one check failed (prints detailed failure messages)

**Output interpretation:**
- `✓` = check passed
- `✗` = check failed (with error details)
- `○` = neutral result (e.g., "strategy returned None" is valid behavior)

**Failure diagnostics:**
When a check fails, the script prints:
- Which strategy failed (S1-S7)
- Which check group failed (1-6)
- Specific error (e.g., "missing entry_second in signal_data", "param grid has < 2 parameters")
- Python exception type and message for crashes

**Check coverage:**
1. **Import checks**: Verifies `shared.strategies.SN.config` and `shared.strategies.SN.strategy` modules import
2. **Instantiation checks**: Verifies `get_default_config()` + `SNStrategy(cfg)` succeeds and metadata matches
3. **Parameter grid checks**: Verifies `get_param_grid()` returns dict with 2+ params, each param has 2+ values
4. **Synthetic evaluation checks**: Tests 4 patterns (spike, flat, nan_heavy, extreme) to verify no crashes
5. **Signal structure checks**: Verifies returned signals have direction ∈ {Up, Down}, entry_price ∈ [0.01, 0.99], entry_second in signal_data
6. **Edge case checks**: Verifies strategies return None (not crash) for sparse data (5 valid ticks in 300s)

## Deviations

None. Implemented exactly as specified in task plan.

## Known Issues

None. All 7 strategies pass all 6 check groups.

## Files Created/Modified

- `scripts/verify_s03_strategies.sh` — Executable verification script with 6 check groups validating all 7 strategies (S1-S7) across imports, instantiation, parameter grids, synthetic evaluation, signal structure, and edge case handling; uses embedded Python for complex checks; exit 0 on success, exit 1 with detailed diagnostics on failure
