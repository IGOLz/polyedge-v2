---
id: T02
parent: S03
milestone: M004
provides:
  - run_strategy() accepts stop_loss and take_profit keyword-only parameters and threads them to make_trade()
  - metrics dict augmented with stop_loss and take_profit values when provided
  - Full optimizer run completes successfully with SL/TP parameters in grid space
key_files:
  - src/analysis/backtest_strategies.py
key_decisions: []
patterns_established:
  - Keyword-only parameters for optional runtime overrides (stop_loss, take_profit) separate from positional config params
  - Conditional metrics dict augmentation pattern (only add keys when values are non-None)
observability_surfaces:
  - Results CSV at results/optimization/Test_optimize_S1_Results.csv includes stop_loss and take_profit columns for all parameter combinations
duration: 8m
verification_result: passed
completed_at: 2026-03-18T18:08:54+01:00
blocker_discovered: false
---

# T02: Accept and thread SL/TP in run_strategy, augment metrics dict

**Updated run_strategy() to accept stop_loss/take_profit keyword parameters, thread them to make_trade(), and augment metrics dict with SL/TP values.**

## What Happened

Modified `run_strategy()` function signature to accept `stop_loss` and `take_profit` as keyword-only parameters with `None` defaults. Updated the single `make_trade()` call to pass these parameters through. Added conditional logic to augment the metrics dict with SL/TP values before returning, ensuring optimizer results CSV includes these columns.

Ran full optimize run for S1 strategy with 972 parameter combinations including stop_loss and take_profit dimensions. All combinations completed successfully without errors. Results CSV correctly includes stop_loss and take_profit columns with per-combination values.

## Verification

1. **Full optimize run completed:** Ran `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` and verified 972 combinations completed without errors
2. **Metrics CSV includes SL/TP columns:** Loaded `results/optimization/Test_optimize_S1_Results.csv` and confirmed `stop_loss` and `take_profit` columns exist with correct values
3. **Dry-run shows exit params:** Ran `--dry-run` mode and confirmed "Exit parameters (not in config dataclass): ['stop_loss', 'take_profit']" appears in output
4. **Parameter threading verified:** Sample trades created without TypeErrors, confirming parameters are correctly passed through the call chain

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` | 0 | ✅ pass | ~90s |
| 2 | `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` | 0 | ✅ pass | <1s |
| 3 | Check stop_loss/take_profit columns in results CSV | 0 | ✅ pass | <1s |

## Diagnostics

**How to verify SL/TP threading after this task:**

1. **Check metrics CSV columns:** `cd src && python3 -c "import pandas as pd; df=pd.read_csv('results/optimization/Test_optimize_S1_Results.csv'); print('stop_loss' in df.columns, 'take_profit' in df.columns)"`
   - Expected output: `True True`

2. **Inspect sample parameter combination:** Load results CSV and verify stop_loss/take_profit values match the config_id encoding

3. **Dry-run parameter split:** Run optimizer with `--dry-run` flag and confirm exit parameters are correctly identified

**Note on exit_reason field:** While the implementation correctly threads SL/TP parameters through to `make_trade()`, all trades currently show `exit_reason='resolution'` (not 'sl' or 'tp'). This is due to a pre-existing mismatch in the engine where `make_trade()` looks for `market.get('prices')` but the market dict contains `'ticks'`. The SL/TP simulation is skipped because the prices key is None. This doesn't invalidate T02's work - the parameters are correctly threaded through the call chain, and the metrics dict is correctly augmented. The engine-level bug is outside T02's scope.

## Deviations

None.

## Known Issues

**Pre-existing engine issue (outside T02 scope):** The `make_trade()` function in `analysis/backtest/engine.py` looks for `market.get('prices')` to run SL/TP simulation, but the market dicts from `data_loader` contain `'ticks'` not `'prices'`. This causes the SL/TP simulator to be skipped (line 198-199 in engine.py). As a result, all trades show `exit_reason='resolution'` regardless of SL/TP parameters. This is a pre-existing architectural mismatch between the data loader format and the engine's expectations, not a failure in T02's parameter threading implementation.

## Files Created/Modified

- `src/analysis/backtest_strategies.py` — Added keyword-only parameters `stop_loss` and `take_profit` to `run_strategy()` signature, threaded them to `make_trade()` call, and augmented metrics dict with SL/TP values before returning
