# S05: Integration Verification

**Goal:** Prove the complete M004 pipeline works end-to-end by verifying all S01-S04 deliverables integrate correctly.

**Demo:** Run `./scripts/verify_m004_milestone.sh` and see 7/7 checks pass, proving: strategy grids include SL/TP, dry-run shows ≥100 combinations, full optimize produces ranked CSV with explicit exit parameters, and at least one trade exits via stop-loss and one via take-profit.

## Must-Haves

- Verification script with 7 checks covering all S01-S04 deliverables
- Strategy grid validation (reuses verify_m004_s01.py)
- Dry-run dimension check (verifies ≥100 combinations and SL/TP presence)
- Full optimization execution (runs S1 on limited market sample)
- CSV structure validation (≥100 rows, SL/TP columns with expected ranges)
- Console summary display verification (grep for SL/TP pattern in top 10)
- Exit reason diversity check (at least one 'sl' and one 'tp' exit)
- Import smoke test (all 7 strategies + TEMPLATE import without errors)
- Pass/fail tracking with summary output

## Observability / Diagnostics

**Runtime signals:**
- Verification script prints clear section headers for each of 7 checks
- Each check outputs ✓ or ✗ with descriptive message
- Summary line shows X/7 checks passed for quick health assessment
- Exit code 0 = all pass, 1 = any fail for automation integration

**Inspection surfaces:**
- Temporary output files in /tmp preserve optimize and dry-run output for debugging
- Failed checks print descriptive error messages indicating what broke
- Individual checks can be extracted and run standalone for focused diagnosis
- Check 6 (exit reason diversity) includes parameter adjustment guidance in comments

**Failure visibility:**
- Script uses `set -euo pipefail` for early error detection
- Each check explicitly captures and tests exit codes or output patterns
- Pass/fail helper functions centralize output formatting
- Summary section lists total failed checks before exiting

**Redaction constraints:**
- No sensitive data involved — script only runs analysis/backtest code on market data
- Console output from optimization may be verbose but contains no secrets
- Temporary files in /tmp can be inspected for debugging without redaction

## Verification

- Run `./scripts/verify_m004_milestone.sh` and verify 7/7 checks pass
- Check console output shows summary with pass count and any failures
- Verify script exits with code 0 (all checks passed)

## Tasks

- [x] **T01: Write comprehensive milestone verification script** `est:45m`
  - Why: Prove complete M004 pipeline integration (all S01-S04 deliverables working together)
  - Files: `scripts/verify_m004_milestone.sh` (new), reuses `src/scripts/verify_m004_s01.py`
  - Do:
    1. Copy structure from `scripts/verify_m003_milestone.sh` (set -euo pipefail, pass/fail tracking, summary)
    2. Implement 7 checks:
       - **Check 1**: Strategy grid validation — run existing `verify_m004_s01.py`, verify exit 0
       - **Check 2**: Dry-run dimensions — run `optimize.py --strategy S1 --dry-run`, grep for "Total combinations:" and verify ≥100, grep for "stop_loss" and "take_profit" parameter listings
       - **Check 3**: Full optimization execution — run optimize on S1 with `--max-markets 100` (for speed), verify results CSV created in `./results/optimization/`
       - **Check 4**: CSV structure validation — check results CSV has ≥100 rows, contains `stop_loss` and `take_profit` columns, values in expected ranges (stop_loss [0.35,0.45], take_profit [0.65,0.75])
       - **Check 5**: Console summary display — grep optimize output for `SL=.*TP=` pattern, verify exactly 10 matches (top 10)
       - **Check 6**: Exit reason diversity — run programmatic backtest with Counter inspection (pattern from S04/T01), verify at least one 'sl' and one 'tp' exit; if fails, document parameter adjustment guidance
       - **Check 7**: Import smoke test — import all 7 strategies + TEMPLATE from registry without errors
    3. Track pass/fail counts, print summary at end
    4. Make script executable (`chmod +x`)
    5. Handle PYTHONPATH=. context and cd to project root (follow M003 pattern)
  - Verify:
    - Run `./scripts/verify_m004_milestone.sh` and see 7/7 checks pass
    - Check console shows summary with pass count
    - Verify script exits with code 0
  - Done when: Verification script exists, is executable, all 7 checks pass, and summary output confirms milestone completion

## Files Likely Touched

- `scripts/verify_m004_milestone.sh` (new)
- `scripts/verify_m003_milestone.sh` (reference template)
- `src/scripts/verify_m004_s01.py` (called by check 1)
