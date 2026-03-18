---
id: S03-UAT
parent: S03
milestone: M004
written: 2026-03-18T18:08:54+01:00
---

# S03: Grid Search Orchestrator — UAT

**Milestone:** M004
**Written:** 2026-03-18

## UAT Type

- UAT mode: live-runtime
- Why this mode is sufficient: Grid search orchestrator must run real backtests with market data to verify parameter combinations are generated correctly, exit params are threaded through all layers, and results CSV contains stop_loss/take_profit columns

## Preconditions

- Working directory: `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M004`
- S01 deliverables exist: All 7 strategies (S1-S7) have `get_param_grid()` returning dicts with stop_loss and take_profit keys
- S02 deliverables exist: Engine has `simulate_sl_tp_exit()` function and Trade dataclass with `exit_reason` field
- Market data available in database for backtesting

## Smoke Test

Run dry-run mode for S1 strategy and verify it shows ≥100 combinations with stop_loss and take_profit dimensions listed:

```bash
cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run
```

**Expected:** Output shows "Total combinations: 972" with stop_loss: [0.35, 0.4, 0.45] and take_profit: [0.65, 0.7, 0.75] in parameter list, and "Exit parameters (not in config dataclass): ['stop_loss', 'take_profit']"

## Test Cases

### 1. Dry-run shows correct grid dimensions

1. Navigate to src directory: `cd src`
2. Run optimizer in dry-run mode: `PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run`
3. **Expected:** 
   - Output shows 7 parameters (5 strategy-specific + 2 exit params)
   - stop_loss: [0.35, 0.4, 0.45]
   - take_profit: [0.65, 0.7, 0.75]
   - Total combinations: 972
   - Exit parameters identified: ['stop_loss', 'take_profit']

### 2. Full optimize run completes without errors

1. Navigate to src directory: `cd src`
2. Run full optimizer for S1: `PYTHONPATH=. python3 -m analysis.optimize --strategy S1`
3. Wait for completion (may take 60-90 seconds for 972 combinations)
4. **Expected:**
   - No TypeErrors about unexpected keyword arguments
   - No errors about missing parameters
   - Process completes with exit code 0
   - Results CSV created at `results/optimization/Test_optimize_S1_Results.csv`

### 3. Results CSV includes stop_loss and take_profit columns

1. Navigate to src directory: `cd src`
2. Run Python check: `python3 -c "import pandas as pd; df=pd.read_csv('results/optimization/Test_optimize_S1_Results.csv'); print('stop_loss' in df.columns, 'take_profit' in df.columns)"`
3. **Expected:** Output shows `True True`

### 4. Results CSV has correct number of rows and unique SL/TP values

1. Navigate to src directory: `cd src`
2. Run Python check:
   ```python
   python3 -c "
   import pandas as pd
   df = pd.read_csv('results/optimization/Test_optimize_S1_Results.csv')
   print(f'Total rows: {len(df)}')
   print(f'Unique stop_loss values: {sorted(df[\"stop_loss\"].unique())}')
   print(f'Unique take_profit values: {sorted(df[\"take_profit\"].unique())}')
   "
   ```
3. **Expected:**
   - Total rows: 972
   - Unique stop_loss values: [0.35, 0.4, 0.45]
   - Unique take_profit values: [0.65, 0.7, 0.75]

### 5. config_id encoding includes SL/TP values

1. Navigate to src directory: `cd src`
2. Run Python check to inspect sample config_ids:
   ```python
   python3 -c "
   import pandas as pd
   df = pd.read_csv('results/optimization/Test_optimize_S1_Results.csv')
   print(df[['config_id', 'stop_loss', 'take_profit']].head(3).to_string(index=False))
   "
   ```
3. **Expected:** config_id values end with `_stop_loss=X.XX_take_profit=Y.YY` matching the corresponding column values

### 6. Dry-run works for multiple strategies

1. Navigate to src directory: `cd src`
2. Run dry-run for S2: `PYTHONPATH=. python3 -m analysis.optimize --strategy S2 --dry-run`
3. **Expected:**
   - Different total combinations (648 for S2)
   - stop_loss and take_profit dimensions present
   - Exit parameters correctly identified

## Edge Cases

### Dataclass introspection with minimal strategy

1. Create a minimal strategy config with only 1 entry parameter:
   ```python
   @dataclass
   class MinimalConfig:
       threshold: float
   
   def get_param_grid():
       return {
           'threshold': [0.5, 0.6],
           'stop_loss': [0.3, 0.4],
           'take_profit': [0.7, 0.8]
       }
   ```
2. Run dry-run with this strategy
3. **Expected:**
   - Introspection identifies only 'threshold' as config field
   - stop_loss and take_profit correctly identified as exit params
   - Total combinations: 2 × 2 × 2 = 8

### Strategy with no exit params in grid (backward compatibility)

1. If a strategy's `get_param_grid()` returns only entry params (no stop_loss/take_profit)
2. Run optimizer for that strategy
3. **Expected:**
   - No exit params identified
   - run_strategy() called with stop_loss=None, take_profit=None
   - No stop_loss/take_profit columns in results CSV (or NaN values)

## Failure Signals

- **TypeError about unexpected keyword arguments in dataclasses.replace()** → param_dict split failed; strategy params include exit params incorrectly
- **Missing stop_loss or take_profit columns in results CSV** → metrics dict augmentation failed in run_strategy()
- **All exit_reason values are 'resolution'** → exit params not threaded to make_trade(), or market dict key mismatch (known issue documented in S03-SUMMARY.md)
- **Dry-run output missing "Exit parameters" line** → dataclass introspection logic not executed
- **Total combinations count doesn't match expected product** → grid generation or Cartesian product logic broken

## Requirements Proved By This UAT

- R026 (Grid search generates Cartesian product including SL/TP dimensions) — Dry-run and full run prove Cartesian product includes stop_loss and take_profit dimensions; results CSV proves parameters are threaded through the pipeline and augmented into metrics dict

## Not Proven By This UAT

- **Actual SL/TP simulation correctness:** While parameters are correctly threaded through the pipeline, the engine currently has a market dict key mismatch (`'prices'` vs `'ticks'`) that prevents SL/TP simulation from running. All trades show exit_reason='resolution' regardless of SL/TP values. This is a pre-existing engine issue documented in S03-SUMMARY.md, not a failure of the grid search orchestrator.

- **Live trading integration:** This UAT only proves backtest analysis works; live trading bot integration of SL/TP is out of scope (R033)

## Notes for Tester

- **Runtime:** Full optimize run for S1 takes 60-90 seconds for 972 combinations. This is normal for grid search with real market data.

- **Known limitation:** All trades will show exit_reason='resolution' even though stop_loss and take_profit parameters are correctly passed. This is due to a market dict key mismatch in the engine (it expects `'prices'` but gets `'ticks'`). The grid search orchestrator is working correctly — the engine just isn't using the parameters yet. This will be fixed in S04 or a follow-up task.

- **Results CSV location:** The output CSV is at `src/results/optimization/Test_optimize_S1_Results.csv` (note: run from src directory, so path is relative to src/)

- **Dry-run is fast:** Use `--dry-run` mode for quick verification of grid generation without waiting for full backtest
