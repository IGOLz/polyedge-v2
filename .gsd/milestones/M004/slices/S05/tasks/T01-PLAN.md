# T01: Write comprehensive milestone verification script

**Estimated effort:** 45m

## Description

Write `scripts/verify_m004_milestone.sh` with 7 checks that prove the complete M004 pipeline works end-to-end. This is the final gate for the milestone — every deliverable from S01-S04 must integrate correctly.

The script follows M003's verification pattern (set -euo pipefail, pass/fail tracking, summary output) but adapts checks to M004's specific deliverables: strategy grid validation, dry-run parameter enumeration, full optimization execution, CSV structure, console summary display, exit reason diversity, and import smoke test.

This task closes the milestone by providing authoritative proof that all requirements are met.

## Steps

1. **Copy M003 verification structure**
   - Read `scripts/verify_m003_milestone.sh` to understand pass/fail tracking pattern
   - Start new `scripts/verify_m004_milestone.sh` with header: `#!/bin/bash`, `set -euo pipefail`
   - Add variables: `PASS_COUNT=0`, `FAIL_COUNT=0`, `TOTAL_CHECKS=7`
   - Add helper function: `check_pass() { echo "✓ $1"; ((PASS_COUNT++)); }`
   - Add helper function: `check_fail() { echo "✗ $1"; ((FAIL_COUNT++)); }`
   - Add `cd "$(dirname "$0")/.." || exit 1` to ensure correct working directory

2. **Implement Check 1: Strategy grid validation**
   - Print section header: "Check 1: Strategy grid validation"
   - Run: `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py`
   - Capture exit code with `$?`
   - If exit 0: `check_pass "All strategies have SL/TP in grid"`
   - Else: `check_fail "Strategy grid validation failed"`

3. **Implement Check 2: Dry-run dimensions**
   - Print section header: "Check 2: Dry-run parameter enumeration"
   - Run: `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run > /tmp/dryrun_output.txt 2>&1`
   - Grep for "Total combinations:" and extract number
   - Verify ≥100 (S1 has 972 combinations)
   - Grep for "stop_loss" and "take_profit" in parameter listing section
   - If both pass: `check_pass "Dry-run shows ≥100 combinations with SL/TP"`
   - Else: `check_fail "Dry-run dimension check failed"`

4. **Implement Check 3: Full optimization execution**
   - Print section header: "Check 3: Full optimization execution"
   - Run: `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --max-markets 100 > /tmp/optimize_output.txt 2>&1`
   - Check if results CSV exists: `ls -la results/optimization/*S1*Results.csv 2>/dev/null`
   - If file exists: `check_pass "Optimization produced results CSV"`
   - Else: `check_fail "Optimization failed or no CSV generated"`

5. **Implement Check 4: CSV structure validation**
   - Print section header: "Check 4: CSV structure validation"
   - Find results CSV: `CSV_FILE=$(ls -t src/results/optimization/*S1*Results.csv 2>/dev/null | head -1)`
   - Count rows (excluding header): `ROW_COUNT=$(tail -n +2 "$CSV_FILE" | wc -l)`
   - Verify ≥100 rows
   - Check for stop_loss column: `head -1 "$CSV_FILE" | grep -q "stop_loss"`
   - Check for take_profit column: `head -1 "$CSV_FILE" | grep -q "take_profit"`
   - Verify value ranges with awk/grep (stop_loss in [0.35,0.45], take_profit in [0.65,0.75])
   - If all pass: `check_pass "CSV has ≥100 rows with SL/TP columns"`
   - Else: `check_fail "CSV structure validation failed"`

6. **Implement Check 5: Console summary display**
   - Print section header: "Check 5: Console summary SL/TP display"
   - Grep optimize output for `SL=.*TP=` pattern: `grep -c "SL=[0-9.]\+, TP=[0-9.]\+" /tmp/optimize_output.txt`
   - Verify exactly 10 matches (top 10 ranked combinations)
   - If 10: `check_pass "Console shows SL/TP for top 10"`
   - Else: `check_fail "Console SL/TP display check failed (expected 10, got $COUNT)"`

7. **Implement Check 6: Exit reason diversity**
   - Print section header: "Check 6: Exit reason diversity"
   - Create temporary Python script that:
     - Imports data_loader, backtest_strategies, registry
     - Loads S1 strategy and 50 markets
     - Runs backtest with stop_loss=0.4, take_profit=0.7
     - Collects exit_reason values with Counter
     - Checks for at least one 'sl' and one 'tp'
     - Prints result and exits 0 if both present, 1 otherwise
   - Run script: `cd src && PYTHONPATH=. python3 /tmp/check_exit_reasons.py`
   - If exit 0: `check_pass "At least one SL and one TP exit observed"`
   - Else: `check_fail "Exit reason diversity check failed (adjust test parameters if needed)"`
   - Note: Include comment in script about parameter sensitivity (see S05-RESEARCH.md common pitfalls)

8. **Implement Check 7: Import smoke test**
   - Print section header: "Check 7: Strategy import smoke test"
   - Create temporary Python script that:
     - Imports registry.discover_strategies()
     - Calls discover_strategies() and checks return has 8 entries (S1-S7 + TEMPLATE)
     - Tries to import each strategy's config and strategy modules
     - Exits 0 if all succeed, 1 otherwise
   - Run script: `cd src && PYTHONPATH=. python3 /tmp/check_imports.py`
   - If exit 0: `check_pass "All strategies import without errors"`
   - Else: `check_fail "Import smoke test failed"`

9. **Add summary section**
   - Print separator line: `echo "========================================"`
   - Print results: `echo "Milestone M004 verification: $PASS_COUNT/$TOTAL_CHECKS checks passed"`
   - If FAIL_COUNT > 0: `echo "Failed checks: $FAIL_COUNT" && exit 1`
   - Else: `echo "✓ Milestone verification complete" && exit 0`

10. **Make executable and test**
    - Run: `chmod +x scripts/verify_m004_milestone.sh`
    - Run script: `./scripts/verify_m004_milestone.sh`
    - Verify all 7 checks pass
    - Check console output is clear and summary is correct
    - If any check fails, debug and fix (most likely Check 6 parameter sensitivity)

## Must-Haves

- Script exists at `scripts/verify_m004_milestone.sh` and is executable
- Uses `set -euo pipefail` for early error detection
- All 7 checks implemented with clear section headers
- Pass/fail tracking with helper functions
- Summary output shows X/7 checks passed
- Script exits 0 if all pass, 1 if any fail
- Proper PYTHONPATH=. and working directory handling
- Exit reason diversity check includes parameter adjustment guidance in comments

## Verification

```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004
./scripts/verify_m004_milestone.sh
```

Expected output:
- 7 section headers with check descriptions
- 7 ✓ symbols for passed checks
- Summary line: "Milestone M004 verification: 7/7 checks passed"
- Final line: "✓ Milestone verification complete"
- Script exits with code 0

If Check 6 fails consistently (all exits are 'resolution' or all 'sl'), the test parameters need adjustment. See S05-RESEARCH.md "Common Pitfalls" section for guidance.

## Inputs

From previous slices:
- `src/scripts/verify_m004_s01.py` — S01 grid validation script (called by Check 1)
- `src/analysis/optimize.py` — CLI entry point with --strategy and --dry-run flags
- `src/analysis/backtest_strategies.py` — provides run_strategy() for programmatic backtest
- `src/analysis/backtest/data_loader.py` — provides load_all_data() for market loading
- `src/shared/strategies/registry.py` — provides discover_strategies() for import test

From M003:
- `scripts/verify_m003_milestone.sh` — reference template with 8 checks and pass/fail tracking

## Expected Output

New file:
- `scripts/verify_m004_milestone.sh` — executable shell script with 7 checks

Console output when run:
```
Check 1: Strategy grid validation
✓ All strategies have SL/TP in grid

Check 2: Dry-run parameter enumeration
✓ Dry-run shows ≥100 combinations with SL/TP

Check 3: Full optimization execution
✓ Optimization produced results CSV

Check 4: CSV structure validation
✓ CSV has ≥100 rows with SL/TP columns

Check 5: Console summary SL/TP display
✓ Console shows SL/TP for top 10

Check 6: Exit reason diversity
✓ At least one SL and one TP exit observed

Check 7: Strategy import smoke test
✓ All strategies import without errors

========================================
Milestone M004 verification: 7/7 checks passed
✓ Milestone verification complete
```

Exit code: 0

## Observability Impact

**Diagnostic surface created:**
- Script provides authoritative milestone verification command
- Each check has clear pass/fail output with section headers
- Summary line gives quick health check: X/7 passed
- Failed checks print descriptive error messages

**Future debugging:**
- If milestone verification fails after changes, run script to see which check broke
- Check 6 (exit reason diversity) is most sensitive to parameter changes — if fails, consult comments in script for adjustment guidance
- Individual checks can be extracted and run standalone for focused debugging

**Fragile points:**
- Check 6 depends on actual price movements in loaded markets — stochastic by nature
- Check 4 CSV validation assumes S1 parameter ranges unchanged (stop_loss [0.35,0.45], take_profit [0.65,0.75])
- All Python checks assume PYTHONPATH=. and correct working directory context
