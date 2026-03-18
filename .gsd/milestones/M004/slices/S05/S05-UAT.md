---
id: S05-UAT
parent: S05
milestone: M004
written: 2026-03-18T20:31:00Z
---

# S05: Integration Verification — UAT

**Milestone:** M004
**Written:** 2026-03-18

## UAT Type

- **UAT mode:** artifact-driven
- **Why this mode is sufficient:** This slice delivers a verification script that proves integration correctness through automated checks. The script itself is the artifact under test — it must run successfully and report 7/7 checks passed.

## Preconditions

- Working directory is `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004`
- All S01-S04 deliverables are in place:
  - Strategy grids with SL/TP parameters (S01)
  - Engine SL/TP simulation functions (S02)
  - Grid search orchestrator with SL/TP integration (S03)
  - Working SL/TP simulation with CSV and console output (S04)
- Python environment has all dependencies installed
- Historical market data available in database (for exit reason diversity check)

## Smoke Test

Run verification script and verify it completes with exit code 0:

```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004
./scripts/verify_m004_milestone.sh
echo $?  # Should print 0
```

Expected: Script prints 7 check sections with ✓ status, summary shows "7/7 checks passed", exit code is 0.

## Test Cases

### 1. Complete verification run

1. Navigate to M004 worktree: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004`
2. Run verification script: `./scripts/verify_m004_milestone.sh`
3. Observe output for each of 7 checks
4. **Expected:**
   - Check 1 (Strategy grid validation): ✓ All strategies have SL/TP in grid
   - Check 2 (Dry-run enumeration): ✓ Dry-run shows ≥100 combinations (972) with SL/TP
   - Check 3 (Optimization execution): ✓ Optimization results CSV exists
   - Check 4 (CSV structure): ✓ CSV has ≥100 rows (972) with SL/TP columns in expected ranges
   - Check 5 (Console summary): ✓ Console shows SL/TP for top 10
   - Check 6 (Exit reason diversity): ✓ At least one SL and one TP exit observed
   - Check 7 (Import smoke test): ✓ All strategies import without errors
   - Summary line: "Milestone M004 verification: 7/7 checks passed"
   - Exit code: 0

### 2. Strategy grid validation (Check 1)

1. Run just check 1 logic manually: `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py`
2. **Expected:**
   - Script prints "✓ All strategies have stop_loss and take_profit in parameter grids"
   - Exit code 0
   - All 7 strategies (S1-S7) plus TEMPLATE confirmed to have SL/TP parameters

### 3. Dry-run parameter enumeration (Check 2)

1. Run dry-run manually: `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run > /tmp/dryrun_output.txt 2>&1`
2. Check output: `cat /tmp/dryrun_output.txt | grep "Total combinations:"`
3. Check SL/TP parameters: `grep -E "stop_loss|take_profit" /tmp/dryrun_output.txt`
4. **Expected:**
   - Output shows "Total combinations: 972"
   - Output lists stop_loss parameter with 3 values
   - Output lists take_profit parameter with 3 values

### 4. CSV structure validation (Check 4)

1. Locate results CSV: `ls -la src/results/optimization/*S1*Results.csv | head -1`
2. Count rows: `wc -l <csv_path>`
3. Check columns: `head -1 <csv_path> | grep -o "stop_loss\|take_profit"`
4. Sample values: `tail -n +2 <csv_path> | cut -d',' -f<stop_loss_col> | sort -u`
5. **Expected:**
   - CSV has ≥100 rows (excluding header)
   - Header row contains both "stop_loss" and "take_profit" columns
   - stop_loss values are in [0.35, 0.40, 0.45]
   - take_profit values are in [0.65, 0.70, 0.75]

### 5. Exit reason diversity (Check 6)

1. Run exit reason check manually:
   ```python
   cd src
   python3 -c "
   import sys
   sys.path.insert(0, '.')
   from analysis.data_loader import load_all_data
   from shared.strategies.S1.strategy import S1
   from shared.strategies.S1.config import get_default_config
   from analysis.backtest.engine import run_strategy
   from collections import Counter
   
   markets = load_all_data()[:50]
   config = get_default_config()
   strategy = S1(config)
   
   results = run_strategy('S1', markets, config, stop_loss=0.4, take_profit=0.7)
   
   exit_reasons = Counter(trade.exit_reason for trade in results['trades'])
   print(f'Exit reasons: {dict(exit_reasons)}')
   print(f'SL exits: {exit_reasons[\"sl\"]}')
   print(f'TP exits: {exit_reasons[\"tp\"]}')
   "
   ```
2. **Expected:**
   - Output shows non-zero count for both 'sl' and 'tp' exit reasons
   - Example: `Exit reasons: {'sl': 32, 'tp': 1}` (exact counts may vary with data)

### 6. Import smoke test (Check 7)

1. Run import test manually:
   ```python
   cd src
   python3 -c "
   import sys
   sys.path.insert(0, '.')
   from shared.strategies.registry import discover_strategies, load_strategy
   
   strategies = discover_strategies()
   print(f'Discovered strategies: {strategies}')
   
   for sid in strategies:
       try:
           strategy = load_strategy(sid)
           print(f'✓ {sid} imports successfully')
       except Exception as e:
           print(f'✗ {sid} import failed: {e}')
   "
   ```
2. **Expected:**
   - Output shows 8 strategies discovered: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'TEMPLATE']
   - All 8 strategies print "✓ imports successfully"
   - No import errors or exceptions

## Edge Cases

### Optimization execution with missing CSV

If results CSV doesn't exist (e.g., fresh clone), check 3 should run full optimization:

1. Delete results CSV: `rm src/results/optimization/*S1*Results.csv`
2. Run verification script: `./scripts/verify_m004_milestone.sh`
3. **Expected:**
   - Check 3 output shows "Running optimization..." instead of "(Using existing results CSV)"
   - Optimization runs on filtered market subset (btc 5m)
   - Check 3 passes after optimization completes
   - New CSV file created in `src/results/optimization/`

### Low volatility market data (Check 6 sensitivity)

If market data has low volatility and take_profit thresholds are rarely hit:

1. Check 6 may show very skewed distribution (e.g., 40 SL exits, 0 TP exits)
2. **Expected:**
   - Check 6 should fail with message "Exit reason diversity check failed: no tp exits"
   - Script comments document parameter adjustment guidance:
     - Lower take_profit threshold (e.g., 0.6 instead of 0.7)
     - Or increase stop_loss threshold (e.g., 0.45 instead of 0.4)
     - Or increase market sample size (100 markets instead of 50)

### Strategy import failure

If a strategy has syntax errors or missing dependencies:

1. Introduce error: `echo "invalid syntax @#$" >> src/shared/strategies/S1/strategy.py`
2. Run verification script: `./scripts/verify_m004_milestone.sh`
3. **Expected:**
   - Check 7 fails with message showing which strategy failed and the error
   - Script exit code is 1 (failure)
   - Summary shows "<7/7 checks passed"

## Failure Signals

- **Check 1 fails:** Strategy grids missing stop_loss or take_profit parameters — inspect `/tmp/grid_check.txt` for details
- **Check 2 fails:** Dry-run shows <100 combinations or missing SL/TP parameters — inspect `/tmp/dryrun_output.txt`
- **Check 3 fails:** Optimization execution error — inspect `/tmp/optimize_output.txt` for traceback
- **Check 4 fails:** CSV missing columns or insufficient rows — inspect results CSV path printed in check 3
- **Check 5 fails:** Console output missing SL/TP display pattern — inspect `/tmp/optimize_output.txt`
- **Check 6 fails:** No stop-loss or take-profit exits observed — inspect exit reason distribution in output; adjust test parameters per script comments
- **Check 7 fails:** Strategy import errors — inspect error message showing which strategy failed and why (module not found, syntax errors)
- **Script exits with code 1:** One or more checks failed — summary line shows X/7 checks passed (X < 7)

## Requirements Proved By This UAT

This UAT proves M004 requirements are validated through end-to-end integration:

- **R023** — All strategies declare stop_loss and take_profit parameter ranges (Check 1)
- **R024** — TEMPLATE demonstrates SL/TP pattern with documented semantics (Checks 1, 7)
- **R025** — Engine simulates SL/TP exits by tracking price every second (Check 6 proves exits occur)
- **R026** — Grid search generates Cartesian product including SL/TP dimensions (Check 2)
- **R027** — Backtest output CSV includes stop_loss, take_profit columns (Check 4)
- **R028** — Top 10 summary prints explicit SL/TP values (Check 5)
- **R029** — Strategy-specific SL/TP ranges are tuned to typical entry prices (Check 4 validates ranges)
- **R030** — TEMPLATE provides clear example with documented semantics (Check 7)
- **R031** — Trades distinguish SL exit vs TP exit vs hold-to-resolution (Check 6 proves diverse exit reasons)

## Not Proven By This UAT

- **Strategy profitability or quality** — Verification proves integration correctness but doesn't validate whether SL/TP parameters improve performance. That requires separate analysis.
- **Live trading bot integration** — M004 is backtest-only; live trading integration is out of scope (R033).
- **Trailing stop loss** — Deferred to future milestone (R032).
- **Parameter optimization effectiveness** — Script proves parameter grid includes SL/TP and produces diverse results, but doesn't validate whether grid search finds optimal combinations. That's a research question.

## Notes for Tester

- **Runtime:** Full verification takes ~15-20 seconds when results CSV exists. If CSV missing, check 3 runs full optimization which takes ~10-20 minutes.
- **Exit reason asymmetry:** Check 6 typically shows highly skewed distribution (SL exits dominate TP exits). This reflects real market behavior — stop-loss thresholds are hit more frequently than take-profit thresholds given current strategy entry prices and SL/TP ranges. As long as at least one TP exit occurs, check passes.
- **Temporary files:** Script generates diagnostic files in `/tmp` for inspection:
  - `/tmp/grid_check.txt` — Strategy grid validation details
  - `/tmp/dryrun_output.txt` — Parameter enumeration output
  - `/tmp/optimize_output.txt` — Full optimization console output (if run)
  - `/tmp/check_exit_reasons.py` — Generated exit reason diversity test script
  - `/tmp/check_imports.py` — Generated import smoke test script
- **CSV location:** Optimization results CSV is in `src/results/optimization/` with filename pattern `*S1*Results.csv`. Check 3 output prints exact path.
- **Known rough edges:** Check 6 parameter thresholds (stop_loss=0.4, take_profit=0.7) are tuned for current market data. If market volatility changes dramatically, may need adjustment per script comments.
