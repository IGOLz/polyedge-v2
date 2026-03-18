# S05 — Research

**Date:** 2026-03-18

## Summary

S05 is integration verification for M004, proving that all four prior slices work together as a complete pipeline. All individual components were validated in S01-S04; this slice assembles a comprehensive verification script that exercises the full stack: strategy grids → dry-run parameter enumeration → full optimization run → CSV output → console summary → exit reason diversity.

The pattern is well-established from M003's `verify_m003_milestone.sh`, which provides a robust template with 8 checks, proper error handling, and summary output. S05 adapts this pattern to M004's deliverables.

## Recommendation

Write `scripts/verify_m004_milestone.sh` as a shell script with 7 checks following M003's structure:

1. **Strategy grid validation** — Import and run existing `src/scripts/verify_m004_s01.py` to prove all 7 strategies + TEMPLATE have SL/TP keys
2. **Dry-run dimensions** — Run `optimize.py --strategy S1 --dry-run`, verify output shows ≥100 combinations and lists stop_loss/take_profit in parameter section
3. **Full optimization execution** — Run optimize on S1 with small market sample (100 markets for speed), verify results CSV created
4. **CSV structure validation** — Check results CSV has ≥100 rows and contains stop_loss/take_profit columns with expected value ranges
5. **Console summary display** — Grep optimize output for `SL=.*TP=` pattern, verify 10 matches (top 10 ranked combinations)
6. **Exit reason diversity** — Run backtest programmatically with Counter inspection (pattern from S04/T01), verify at least one 'sl' and one 'tp' exit
7. **Import smoke test** — Import all 7 strategies + TEMPLATE without errors (reuse M003 check)

Use `set -euo pipefail` for early exit on errors, track pass/fail counts, print summary at end.

## Implementation Landscape

### Key Files

- `scripts/verify_m004_milestone.sh` — new verification script (main deliverable)
- `scripts/verify_m003_milestone.sh` — reference template with 8 checks and summary reporting
- `src/scripts/verify_m004_s01.py` — existing S01 verification script (call from shell script check 1)
- `src/analysis/optimize.py` — CLI entry point with `--strategy` and `--dry-run` flags
- `src/analysis/backtest_strategies.py` — provides `run_strategy()` for programmatic backtest execution
- `src/analysis/backtest/data_loader.py` — provides `load_all_data()` for market loading
- `src/shared/strategies/registry.py` — provides `discover_strategies()` for import smoke test

### Build Order

1. **Copy M003 verification script structure** — provides error handling, pass/fail tracking, summary output
2. **Adapt checks 1-7** — replace M003-specific checks with M004 verification steps
3. **Test each check independently** — run individual Python/bash snippets to verify correctness
4. **Run full script** — execute all checks in sequence, verify summary output

### Verification Approach

Run the verification script:
```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004
chmod +x scripts/verify_m004_milestone.sh
./scripts/verify_m004_milestone.sh
```

Expected output: 7/7 checks passed, milestone verification complete.

**If check 6 (exit reason diversity) fails consistently:**
- The exit reason check depends on actual price movements in loaded markets
- If all trades go to resolution or all hit SL, adjust the stop_loss/take_profit test parameters
- Pattern from S04/T01: `stop_loss=0.4, take_profit=0.7` on 50 markets produced Counter({'sl': 32, 'tp': 1})
- May need to experiment with values or increase market count to get both exit types

## Constraints

- Verification must run in worktree context at `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004`
- PYTHONPATH=. required for all Python imports from src/
- Check 3 (full optimization) should limit to 100 markets for speed — full optimization on all markets takes too long for verification
- Exit reason diversity (check 6) requires database access to load real market price data
- Shell script must use `set -euo pipefail` to catch errors early (M003 pattern)

## Common Pitfalls

- **Dry-run combination count** — S1 has 972 combinations in its grid (3×3×2×2×3×3×3 = 972), well above the ≥100 threshold. Verification check must parse "Total combinations: 972" from dry-run output.

- **CSV row count vs combination count** — The CSV will have ≤972 rows (one per combination), but some combinations may be filtered if they produce zero trades. The check should verify ≥100 rows, not exact equality to grid size.

- **Exit reason stochasticity** — The exit_reason distribution depends on actual price movements in the loaded markets. If the verification fails because all trades have exit_reason='resolution', the test parameters (stop_loss/take_profit values) need adjustment or more markets need loading.

- **Console output buffering** — When running optimize.py and capturing output for grep, ensure stdout is captured correctly. Use `2>&1` to merge stderr if needed.

- **Path context** — The verification script lives in `scripts/` but must `cd` to project root before running Python commands with `PYTHONPATH=.`. Follow M003 pattern: `cd "$(dirname "$0")/.." || exit 1`.

## Sources

- M003 verification pattern: scripts/verify_m003_milestone.sh (8 checks with pass/fail tracking)
- S04 exit reason verification: .gsd/milestones/M004/slices/S04/tasks/T01-SUMMARY.md (Counter inspection pattern)
- S01 grid verification: src/scripts/verify_m004_s01.py (strategy import and grid inspection)
- Optimize CLI usage: src/analysis/optimize.py docstring (lines 7-14)
