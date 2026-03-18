# S04: Exit Simulation Fix & Output Display

**Goal:** Fix market dict key mismatch so SL/TP simulation actually runs, and enhance top 10 output to show explicit stop_loss/take_profit values for each ranked combination.

**Demo:** Run `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` on a small market subset and see (1) exit_reason values showing mix of 'sl', 'tp', and 'resolution' instead of all 'resolution', and (2) top 10 console summary displaying SL=X.XX, TP=Y.YY for each ranked combination.

## Must-Haves

- Market dict key renamed from `'ticks'` to `'prices'` in both data_loader.py and backtest_strategies.py (atomic change to maintain consistency)
- SL/TP simulation runs during backtest (engine's `market.get('prices')` check succeeds)
- Top 10 console summary includes explicit stop_loss and take_profit values alongside existing metrics
- Verification proves exit_reason shows non-uniform values (at least one 'sl', one 'tp', and some 'resolution')

## Verification

1. **After T01 (key fix):**
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import run_strategy
   from analysis.backtest import data_loader
   from shared.strategies import get_strategy
   from collections import Counter
   
   markets = data_loader.load_all_data()
   strategy = get_strategy('S1')
   trades, _ = run_strategy('S1', strategy, markets[:50], stop_loss=0.4, take_profit=0.7)
   
   exit_reasons = Counter(t.exit_reason for t in trades)
   print('Exit reason counts:', exit_reasons)
   assert 'sl' in exit_reasons, 'Expected at least one stop loss exit'
   assert 'tp' in exit_reasons, 'Expected at least one take profit exit'
   assert 'resolution' in exit_reasons, 'Expected at least one resolution exit'
   print('✓ Exit reason diversity verified')
   "
   ```
   Expected: Counter showing mix of 'sl', 'tp', and 'resolution' values; assertions pass.

2. **After T02 (console enhancement):**
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.optimize import optimize_strategy
   from analysis.backtest import data_loader
   
   markets = data_loader.load_all_data()[:100]
   optimize_strategy('S1', markets, './results/optimization')
   " | grep -E 'SL=.*TP='
   ```
   Expected: Top 10 summary lines include `SL=0.XX, TP=0.YY` format.

3. **Integration check:**
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import pandas as pd
   df = pd.read_csv('./results/optimization/Test_optimize_S1_Results.csv')
   assert 'stop_loss' in df.columns, 'Missing stop_loss column'
   assert 'take_profit' in df.columns, 'Missing take_profit column'
   assert 'exit_reason' in df.columns, 'Missing exit_reason column'
   print('✓ CSV columns verified')
   print('Exit reason unique values:', df['exit_reason'].unique())
   "
   ```
   Expected: All columns exist; exit_reason shows ['sl', 'tp', 'resolution'].

## Tasks

- [x] **T01: Fix Market Dict Key Mismatch & Verify SL/TP Simulation** `est:20m`
  - Why: Engine expects `market.get('prices')` but data loader returns `'ticks'`, causing SL/TP simulator to be skipped. This is the root cause blocking R027 and R031 validation.
  - Files: `src/analysis/backtest/data_loader.py`, `src/analysis/backtest_strategies.py`
  - Do: 
    1. Change data_loader.py line 117 from `'ticks': tick_array` to `'prices': tick_array`
    2. Change backtest_strategies.py line 68 from `prices=market["ticks"]` to `prices=market["prices"]`
    3. These changes must be atomic (same commit) to avoid breaking backtest_strategies
  - Verify: Run verification command from Verification section (T01 check) — proves exit_reason shows mix of 'sl', 'tp', and 'resolution'
  - Done when: Verification command succeeds showing at least one trade with exit_reason='sl', one with 'tp', and some with 'resolution'; no KeyError from market dict access

- [x] **T02: Enhance Top 10 Console Summary with SL/TP Display** `est:15m`
  - Why: R028 requires explicit SL/TP values visible in console output; currently only in CSV and Best_Configs.txt
  - Files: `src/analysis/optimize.py`
  - Do:
    1. Modify optimize.py lines 176-184 (top 10 summary print loop)
    2. Add `SL={row.get('stop_loss', 'N/A')}, TP={row.get('take_profit', 'N/A')}` to the output string
    3. Use `.get()` with default to handle cases where SL/TP might not be present
    4. Place SL/TP after the ranking_score field for readability
  - Verify: Run verification command from Verification section (T02 check) — grep for SL/TP pattern in console output
  - Done when: Top 10 summary includes explicit stop_loss and take_profit values for each ranked combination; format is human-readable

## Observability / Diagnostics

**Runtime signals:**
- Exit reason distribution in backtest results (`exit_reason` field on Trade objects: 'sl', 'tp', 'resolution')
- Console output from optimize.py showing top 10 combinations with explicit SL/TP values
- CSV export in `./results/optimization/Test_optimize_S1_Results.csv` with stop_loss, take_profit, exit_reason columns

**Inspection surfaces:**
- Verification commands that run backtest_strategies.run_strategy() and print Counter of exit reasons
- Console grep for `SL=.*TP=` pattern in optimization output
- CSV column presence checks and exit_reason unique value inspection

**Failure visibility:**
- KeyError when accessing market dict keys indicates mismatch still present
- All exit_reason='resolution' indicates SL/TP simulation not running
- Missing SL/TP in console output indicates display enhancement not applied
- AssertionError from verification commands indicates expected exit reason diversity not achieved

**Redaction constraints:**
- None — all data is synthetic market predictions and backtest results

## Files Likely Touched

- `src/analysis/backtest/data_loader.py` (line 117 — rename 'ticks' to 'prices')
- `src/analysis/backtest_strategies.py` (line 68 — update market dict key access)
- `src/analysis/optimize.py` (lines 176-184 — add SL/TP to console summary)
