---
estimated_steps: 4
estimated_files: 1
---

# T02: Accept and thread SL/TP in run_strategy, augment metrics dict

**Slice:** S03 — Grid Search Orchestrator
**Milestone:** M004

## Description

Update run_strategy() in backtest_strategies.py to accept stop_loss and take_profit as keyword-only parameters, pass them to make_trade() calls, and augment the metrics dict with these values before returning. This completes the wiring chain from optimize.py's exit_params through to the engine's make_trade() function, enabling SL/TP values to appear in CSV output (consumed by S04).

## Steps

1. Open `src/analysis/backtest_strategies.py` and locate `run_strategy()` function signature
2. Add keyword-only parameters after existing positional/keyword params: `stop_loss: float | None = None, take_profit: float | None = None`
3. Find all `make_trade()` calls in run_strategy() and add keyword arguments: `make_trade(..., stop_loss=stop_loss, take_profit=take_profit)` (should be ~1-2 call sites)
4. After `metrics = compute_metrics(trades, config_id=strategy_id)` line, augment metrics dict before returning:
   ```python
   if stop_loss is not None:
       metrics['stop_loss'] = stop_loss
   if take_profit is not None:
       metrics['take_profit'] = take_profit
   ```
5. Verify function still returns `tuple[list[Trade], dict]` as expected by optimizer

## Must-Haves

- [ ] run_strategy() signature accepts stop_loss and take_profit as keyword-only parameters with None defaults
- [ ] All make_trade() calls pass stop_loss and take_profit parameters
- [ ] metrics dict augmented with SL/TP values before returning (when non-None)
- [ ] Full optimize run produces trades with exit_reason populated correctly

## Verification

- `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` runs full backtest without errors
- At least one trade CSV exists: `ls -lh results/optimization/optimize_S1_trades_*.csv`
- Verify exit_reason populated: Load a trade CSV with pandas and check `exit_reason` column has values other than just 'resolution' (should see mix of 'sl', 'tp', 'resolution')
- Verify metrics dict includes SL/TP: Load results CSV and confirm `stop_loss` and `take_profit` columns exist

## Observability Impact

- Signals added/changed: metrics dict now includes stop_loss and take_profit keys for all parameter combinations that include these exit params
- How a future agent inspects this: Load results CSV (`results/optimization/Test_optimize_S1_Results.csv`) and check column names with `df.columns.tolist()`
- Failure state exposed: If SL/TP not passed correctly, exit_reason will be 'resolution' for all trades; if metrics augmentation missing, stop_loss/take_profit columns won't exist in results CSV

## Inputs

- `src/analysis/backtest_strategies.py` — Current run_strategy() implementation accepts strategy, markets, slippage, base_rate; needs to accept and thread SL/TP parameters
- T01 deliverable: optimize.py now calls run_strategy() with stop_loss and take_profit keyword arguments
- S02 deliverable: make_trade() accepts stop_loss and take_profit as keyword-only parameters; simulate_sl_tp_exit() populates Trade.exit_reason field

## Expected Output

- `src/analysis/backtest_strategies.py` — Updated run_strategy() function that accepts SL/TP parameters, passes them to make_trade(), and augments metrics dict. Full optimize run produces trades with exit_reason correctly populated and metrics CSV includes stop_loss/take_profit columns.
