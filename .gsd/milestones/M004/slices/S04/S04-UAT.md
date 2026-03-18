---
id: S04
parent: M004
milestone: M004
uat_type: artifact-driven
completed_at: 2026-03-18T20:32:00+01:00
---

# S04: Exit Simulation Fix & Output Display — UAT

**Milestone:** M004
**Written:** 2026-03-18

## UAT Type

- **UAT mode:** artifact-driven
- **Why this mode is sufficient:** This slice delivers data pipeline fixes (market dict key consistency) and output enhancements (console display). Success is verifiable through programmatic checks: exit reason diversity in Trade objects, SL/TP values in console output, and CSV column presence. No runtime services or human-facing UI to test.

## Preconditions

- Working directory: `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004`
- Source code in `src/` directory
- Historical market data available via `data_loader.load_all_data()`
- Python 3 with required packages installed

## Smoke Test

Run S1 backtest with explicit stop_loss and take_profit parameters and verify exit reasons show diversity (not all 'resolution'):

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
assert len(exit_reasons) > 0, 'No trades generated'
assert 'sl' in exit_reasons or 'tp' in exit_reasons, 'Expected early exits with tight SL/TP'
print('✓ Smoke test passed')
"
```

**Expected:** Counter showing at least one 'sl' or 'tp' exit; assertion passes.

## Test Cases

### 1. Market Dict Key Consistency

Verify data_loader returns market dicts with 'prices' key and backtest_strategies consumes it correctly:

1. Load first market from data_loader:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest import data_loader
   markets = data_loader.load_all_data()
   print('Market dict keys:', markets[0].keys())
   assert 'prices' in markets[0], 'Expected prices key in market dict'
   print('✓ Data loader provides prices key')
   "
   ```

2. Run backtest_strategies with the loaded market:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import run_strategy
   from analysis.backtest import data_loader
   from shared.strategies import get_strategy
   
   markets = data_loader.load_all_data()
   strategy = get_strategy('S1')
   trades, _ = run_strategy('S1', strategy, markets[:10], stop_loss=0.4, take_profit=0.7)
   print('✓ Backtest consumed markets without KeyError')
   print(f'Generated {len(trades)} trades')
   "
   ```

**Expected:** 
- Test 1: 'prices' in market dict keys; no KeyError
- Test 2: Backtest runs successfully; generates trades without error

### 2. SL/TP Simulation Active

Verify stop-loss and take-profit simulation produces early exits (not all resolution):

1. Run S1 backtest with tight SL/TP parameters (high probability of early exit):
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
   print('Exit reason distribution:', exit_reasons)
   
   sl_count = exit_reasons.get('sl', 0)
   tp_count = exit_reasons.get('tp', 0)
   res_count = exit_reasons.get('resolution', 0)
   
   print(f'Stop losses: {sl_count}, Take profits: {tp_count}, Resolutions: {res_count}')
   assert sl_count > 0 or tp_count > 0, 'Expected at least one early exit with tight SL/TP'
   print('✓ SL/TP simulation is active')
   "
   ```

2. Run with loose SL/TP parameters (should see more resolution exits):
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import run_strategy
   from analysis.backtest import data_loader
   from shared.strategies import get_strategy
   from collections import Counter
   
   markets = data_loader.load_all_data()
   strategy = get_strategy('S1')
   trades, _ = run_strategy('S1', strategy, markets[:50], stop_loss=0.1, take_profit=2.0)
   
   exit_reasons = Counter(t.exit_reason for t in trades)
   print('Exit reason distribution (loose params):', exit_reasons)
   print('✓ Resolution exits work with loose SL/TP')
   "
   ```

**Expected:**
- Test 1: Counter shows at least one 'sl' or 'tp' exit; not all 'resolution'
- Test 2: Counter shows mix including 'resolution' exits when SL/TP are loose

### 3. Console Output Enhancement

Verify top 10 summary displays explicit stop_loss and take_profit values:

1. Run optimization on subset of markets and check console output:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.optimize import optimize_strategy
   from analysis.backtest import data_loader
   
   markets = data_loader.load_all_data()[:100]
   optimize_strategy('S1', markets, './results/optimization')
   " 2>&1 | tee /tmp/optimize_output.txt
   ```

2. Verify SL/TP pattern in output:
   ```bash
   grep -E 'SL=.*TP=' /tmp/optimize_output.txt | head -10
   ```

3. Count occurrences:
   ```bash
   echo "Lines with SL/TP values: $(grep -cE 'SL=.*TP=' /tmp/optimize_output.txt)"
   ```

**Expected:**
- Test 1: Optimization completes without error
- Test 2: At least 10 lines showing pattern like `SL=0.40, TP=0.75`
- Test 3: Count >= 10 (top 10 combinations display SL/TP)

### 4. CSV Integration

Verify results CSV contains stop_loss and take_profit columns with correct value ranges:

1. Check CSV columns:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import pandas as pd
   df = pd.read_csv('./results/optimization/Test_optimize_S1_Results.csv')
   print('CSV columns:', df.columns.tolist())
   assert 'stop_loss' in df.columns, 'Missing stop_loss column'
   assert 'take_profit' in df.columns, 'Missing take_profit column'
   print('✓ CSV has stop_loss and take_profit columns')
   "
   ```

2. Verify value ranges match strategy grid:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import pandas as pd
   df = pd.read_csv('./results/optimization/Test_optimize_S1_Results.csv')
   print('stop_loss unique values:', sorted(df['stop_loss'].unique()))
   print('take_profit unique values:', sorted(df['take_profit'].unique()))
   
   # S1 grid: stop_loss [0.35, 0.40, 0.45], take_profit [0.65, 0.70, 0.75]
   expected_sl = [0.35, 0.40, 0.45]
   expected_tp = [0.65, 0.70, 0.75]
   
   actual_sl = sorted([float(x) for x in df['stop_loss'].unique()])
   actual_tp = sorted([float(x) for x in df['take_profit'].unique()])
   
   assert actual_sl == expected_sl, f'Expected SL {expected_sl}, got {actual_sl}'
   assert actual_tp == expected_tp, f'Expected TP {expected_tp}, got {actual_tp}'
   print('✓ SL/TP values match strategy grid')
   "
   ```

**Expected:**
- Test 1: CSV contains stop_loss and take_profit columns
- Test 2: Unique values match S1 strategy grid ranges

## Edge Cases

### No Markets Matching Strategy Entry Criteria

Run backtest on markets where strategy never enters:

1. Use strategy with impossible entry conditions or empty market set:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import run_strategy
   from shared.strategies import get_strategy
   
   strategy = get_strategy('S1')
   trades, _ = run_strategy('S1', strategy, [], stop_loss=0.4, take_profit=0.7)
   print(f'Generated {len(trades)} trades from empty market list')
   assert len(trades) == 0, 'Expected no trades from empty market list'
   print('✓ Empty market list handled correctly')
   "
   ```

**Expected:** Zero trades; no errors; graceful handling

### Market Dict Missing 'prices' Key

Verify engine handles backward compatibility (older market dicts without 'prices' key):

1. Manually construct market dict without 'prices' and pass to backtest:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import market_to_snapshot
   from shared.market_types import MarketSnapshot
   import numpy as np
   
   # Market dict without 'prices' key (backward compatibility test)
   market = {
       'market_id': 'test_market',
       'creation_ts': 1000000,
       'end_date': 1000300,
       'resolution_value': 1.0,
       'ticks': np.array([0.5, 0.51, 0.52])
   }
   
   try:
       snapshot = market_to_snapshot(market)
       print('✓ market_to_snapshot handled missing prices key')
   except KeyError as e:
       print(f'✗ KeyError when prices key missing: {e}')
       raise
   "
   ```

**Expected:** Should handle gracefully (either use 'ticks' fallback or raise clear error)

## Failure Signals

- **KeyError on market dict access**: Indicates data_loader and backtest_strategies use different key names (regression)
- **All exit_reason='resolution'**: Indicates SL/TP simulation not running (prices key missing or simulation logic broken)
- **Missing SL/TP in console output**: Indicates optimize.py enhancement not applied or wrong output format
- **CSV missing stop_loss/take_profit columns**: Indicates S03 metrics dict augmentation broken or CSV export not including new columns
- **SL/TP values outside declared ranges**: Indicates parameter grid configuration error or CSV corruption

## Requirements Proved By This UAT

- **R027** (partial): Backtest output CSV includes stop_loss and take_profit columns — proved by test case 4. Note: exit_reason field exists on Trade objects, not in aggregated metrics CSV (by design).
- **R028**: Top 10 summary prints explicit SL/TP values — proved by test case 3.
- **R031** (integration): Trades distinguish SL/TP/resolution exits — proved by test case 2 (already validated in S02, this UAT confirms end-to-end).

## Not Proven By This UAT

- **R025** (core SL/TP simulation logic): Already validated in M004/S02 unit tests. This UAT proves integration, not algorithm correctness.
- **R026** (Cartesian product generation): Already validated in M004/S03. This UAT proves the output display, not grid generation.
- **Live trading integration**: M004 is backtest-only (R033 out of scope).

## Notes for Tester

- **Market data dependency**: Tests require historical market data loaded via `data_loader.load_all_data()`. If no data available, tests will fail with empty market list.
- **Exit reason distribution variability**: Exact counts of 'sl', 'tp', and 'resolution' exits depend on actual price movements in the loaded data. Tests check for presence, not exact counts.
- **CSV path assumption**: Tests assume `./results/optimization/Test_optimize_S1_Results.csv` exists after running optimization. File is created by optimize_strategy() function.
- **Known limitation**: The slice plan incorrectly expected `exit_reason` column in the aggregated metrics CSV. This field correctly exists on individual Trade objects but not in the CSV, which contains per-configuration aggregated metrics. Tests verify the correct behavior.
