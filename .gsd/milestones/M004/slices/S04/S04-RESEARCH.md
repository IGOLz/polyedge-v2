# S04 — Research

**Date:** 2026-03-18

## Summary

S04 needs to fix a market dict key mismatch that prevents SL/TP simulation from running, and then enhance the top 10 output display to show explicit stop_loss and take_profit values for each ranked combination.

The core issue is architectural: the data loader returns market dicts with a `'ticks'` key containing the numpy price array, but the engine's `make_trade()` function looks for `market.get('prices')` on line 198. When this key is missing, the SL/TP simulator is skipped and all trades default to `exit_reason='resolution'`.

The CSV output already includes `stop_loss` and `take_profit` columns (S03 correctly augmented the metrics dict), and the Best_Configs.txt file already displays these values in the detailed per-rank breakdown. The remaining work is to add SL/TP to the console top 10 summary in `optimize.py` and verify that fixing the key mismatch produces non-uniform exit_reason values.

## Recommendation

**Fix the key mismatch with a one-line change** — rename `'ticks'` to `'prices'` in the data loader's market dict construction (line 117 in `data_loader.py`). This is the simplest, most direct fix and aligns the data loader's output with the engine's expectations.

**Extend the top 10 console summary** in `optimize.py` to print `SL={row['stop_loss']}, TP={row['take_profit']}` alongside the existing metrics. This makes the parameter values immediately visible without needing to open the CSV or Best_Configs.txt file.

**Verify non-uniform exit_reason values** by running a small backtest after the key fix and checking that trades show a mix of 'sl', 'tp', and 'resolution' exit reasons.

## Implementation Landscape

### Key Files

- `src/analysis/backtest/data_loader.py` (line 117) — Currently sets `'ticks': tick_array` in the market dict. Change to `'prices': tick_array` to match the engine's expectations.

- `src/analysis/backtest/engine.py` (line 198) — Contains `prices = market.get('prices')` check that gates SL/TP simulation. No change needed if we fix the data loader.

- `src/analysis/optimize.py` (lines 176-184) — Top 10 console summary currently prints config_id, total_bets, win_rate_pct, total_pnl, sharpe_ratio, ranking_score. Add `SL={row['stop_loss']}, TP={row['take_profit']}` to the output string.

- `src/analysis/backtest_strategies.py` (line 68) — Already augments metrics dict with SL/TP values. No change needed.

### Build Order

1. **Fix the key mismatch first** — rename 'ticks' to 'prices' in data_loader.py. This unblocks SL/TP simulation immediately.

2. **Enhance the console summary** — add SL/TP to the top 10 print output in optimize.py. This is a pure display change with no logic dependencies.

3. **Verify exit_reason diversity** — run a small backtest (10-20 markets with SL/TP parameters) and check that trades show 'sl', 'tp', and 'resolution' values. This confirms the simulator is actually running.

### Verification Approach

**Manual verification commands:**

1. After fixing the key mismatch, run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import run_strategy
   from analysis.backtest import data_loader
   from shared.strategies import get_strategy
   
   markets = data_loader.load_all_data()
   strategy = get_strategy('S1')
   trades, _ = run_strategy('S1', strategy, markets[:50], stop_loss=0.4, take_profit=0.7)
   
   from collections import Counter
   print('Exit reason counts:', Counter(t.exit_reason for t in trades))
   print('Sample trade with SL exit:', next((t for t in trades if t.exit_reason == 'sl'), None))
   print('Sample trade with TP exit:', next((t for t in trades if t.exit_reason == 'tp'), None))
   "
   ```
   Expected output: Counter showing mix of 'sl', 'tp', and 'resolution' values (not all 'resolution').

2. After enhancing console output, run optimize dry-run to confirm format:
   ```bash
   cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run
   ```
   Expected output: Grid summary with SL/TP dimensions listed.

3. Run full optimize on a small subset:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.optimize import optimize_strategy
   from analysis.backtest import data_loader
   
   markets = data_loader.load_all_data()[:100]
   optimize_strategy('S1', markets, './results/optimization')
   "
   ```
   Expected output: Top 10 summary includes `SL=X.XX, TP=Y.YY` for each ranked combination.

**Automated verification (optional):** Add a unit test in `tests/test_sl_tp_integration.py` that loads a few markets, runs backtest with SL/TP, and asserts that at least one trade has exit_reason='sl' and one has exit_reason='tp'.

## Constraints

- **Backward compatibility:** The key rename from 'ticks' to 'prices' in the data loader could break other code that reads market dicts. Check for any references to `market['ticks']` outside of the analysis module.

  - ✅ `backtest_strategies.py` line 68: `prices=market["ticks"]` in `market_to_snapshot()` — this will need to be updated to `prices=market["prices"]` to match the rename.
  
  - No other code in `src/analysis/` or `src/shared/` reads `market['ticks']` directly (verified via `rg "market\['ticks'\]" src/`).

- **Data loader semantics:** The numpy array is indexed by elapsed seconds, not raw ticks. The name 'ticks' was always a misnomer — it's a price series, not tick counts. The rename to 'prices' improves semantic clarity.

## Common Pitfalls

- **Forgetting to update backtest_strategies.py:** After renaming 'ticks' to 'prices' in the data loader, the `market_to_snapshot()` function in `backtest_strategies.py` line 68 will break because it reads `market["ticks"]`. Must update this line to `prices=market["prices"]` in the same commit as the data_loader change.

- **Assuming all trades will have SL/TP exits:** Even with correct simulation, many trades will still have `exit_reason='resolution'` if the price never hits the SL or TP thresholds during the market's lifetime. The verification should check for **at least one** SL and TP exit, not expect all trades to exit early.

- **SL/TP values may be None in some rows:** If a parameter combination is tested without SL/TP (e.g., during development or testing), the metrics dict won't have these keys. The console summary must handle missing values gracefully with `row.get('stop_loss', 'N/A')` and `row.get('take_profit', 'N/A')`.

## Open Risks

None. This slice is straightforward mechanical work:
- One-line key rename in data loader
- One-line update in backtest_strategies
- String formatting addition in optimize console output
- Verification that exit_reason shows diversity

The fix is low-risk and directly addresses the pre-existing engine issue flagged in S03's forward intelligence.

## Requirements Advanced

- R027 (Backtest output CSV includes stop_loss, take_profit, and exit_reason columns) — Already delivered by S03 (stop_loss/take_profit in CSV); will be fully validated when exit_reason shows non-uniform values after the key fix.
- R028 (Top 10 summary prints explicit SL/TP values for each ranked combination) — Currently only in Best_Configs.txt; will be advanced when console output includes SL/TP.

## Requirements Validated

After S04 completion:
- R027 — CSV already has stop_loss and take_profit columns (S03); will add exit_reason diversity verification
- R028 — Console top 10 summary will display SL/TP values explicitly
- R031 (Trades distinguish SL exit vs TP exit vs hold-to-resolution in output) — Already delivered by S02 (Trade.exit_reason field), will be validated when simulator runs

## Forward Intelligence for Planner

**What needs to happen:**

1. **T01: Fix Market Dict Key Mismatch**
   - Change `data_loader.py` line 117: `'ticks': tick_array` → `'prices': tick_array`
   - Change `backtest_strategies.py` line 68: `prices=market["ticks"]` → `prices=market["prices"]`
   - These two changes must happen together to avoid breaking backtest_strategies

2. **T02: Enhance Top 10 Console Summary**
   - Modify `optimize.py` lines 176-184 to add SL/TP to the printed summary
   - Current format: `Bets={...}, WR={...}, PnL={...}, Sharpe={...}, Score={...}`
   - New format: Add `SL={row.get('stop_loss', 'N/A')}, TP={row.get('take_profit', 'N/A')}` after Score
   - Use `.get()` with default to handle cases where SL/TP might not be present

3. **T03: Verify Exit Reason Diversity**
   - Write a simple verification script or manual test command
   - Run backtest on 50-100 markets with SL/TP parameters
   - Check that `Counter([t.exit_reason for t in trades])` shows at least one 'sl', one 'tp', and some 'resolution'
   - Document the verification command in the task summary

**Fragile dependencies:**

- The data loader rename affects `backtest_strategies.py` — these changes must be atomic (same commit/task).
- The console summary enhancement assumes `stop_loss` and `take_profit` keys exist in the metrics dict. S03 already ensures this via `backtest_strategies.py` lines 118-121, but the print statement should still use `.get()` for defensive coding.

**What to watch:**

- After the key fix, verify that the engine's line 198 check (`prices = market.get('prices')`) now succeeds and the simulator runs (lines 199-206).
- Check that the exit_reason field is correctly propagated through the Trade object construction (line 227) and saved to CSV (line 519).
- The verification should show a realistic distribution of exit reasons — not 100% SL or 100% TP, but a mix reflecting actual price movements.
