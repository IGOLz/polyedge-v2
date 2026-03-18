# S03: Grid Search Orchestrator

**Goal:** Wire S01's parameter grids (with stop_loss/take_profit keys) into optimize.py grid generation, split parameter dicts into strategy_params (config fields) and exit_params (SL/TP), and pass exit_params through run_strategy() to make_trade(), enabling full grid search including SL/TP dimensions.

**Demo:** Run `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` and verify that the full backtest completes without errors, the grid includes stop_loss and take_profit dimensions (972 combinations), and trades are created with exit_reason populated correctly ('sl', 'tp', or 'resolution').

## Must-Haves

- optimize_strategy() introspects strategy config dataclass to identify which param_dict keys are valid config fields vs exit params
- param_dict split into strategy_params (for dataclasses.replace) and exit_params (stop_loss, take_profit)
- exit_params passed to run_strategy() as keyword-only parameters
- run_strategy() accepts stop_loss=None and take_profit=None, passes them to make_trade()
- run_strategy() augments metrics dict with stop_loss and take_profit values before returning
- Dry-run verification shows ≥100 combinations for S1 including SL/TP dimensions
- Full optimize run for S1 produces trades with exit_reason populated correctly
- No changes to S02 deliverables (Trade dataclass, make_trade signature remain unchanged)

## Proof Level

- This slice proves: integration
- Real runtime required: yes (must run full backtest with market data to verify exit_reason populated)
- Human/UAT required: no

## Verification

- `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` shows "Total combinations: 972" (or similar) with stop_loss and take_profit dimensions listed in grid summary
- `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` runs full backtest without errors
- Inspect trade CSV: `ls -lh results/optimization/optimize_S1_trades_*.csv` shows at least one trade CSV exists
- Load and verify exit_reason: `cd src && python3 -c "import pandas as pd; df=pd.read_csv('results/optimization/optimize_S1_trades_S1_entry_window_start=30_entry_window_end=60_price_low_threshold=0.4_price_high_threshold=0.55_min_deviation=0.05_stop_loss=0.35_take_profit=0.65.csv'); print(df['exit_reason'].value_counts())"` shows mix of 'sl', 'tp', 'resolution'
- Verify metrics dict includes SL/TP: `cd src && python3 -c "import pandas as pd; df=pd.read_csv('results/optimization/Test_optimize_S1_Results.csv'); print('stop_loss' in df.columns, 'take_profit' in df.columns)"` outputs `True True`

## Observability / Diagnostics

- **Runtime signals:** Grid generation dry-run output prints parameter grid dimensions including stop_loss and take_profit ranges; full optimization run prints "Total combinations: N" during execution
- **Inspection surfaces:** Trade CSVs at `results/optimization/optimize_S1_trades_*.csv` contain exit_reason column showing 'sl', 'tp', or 'resolution'; metrics CSV at `results/optimization/Test_optimize_S1_Results.csv` includes stop_loss and take_profit columns with per-combination values
- **Failure visibility:** TypeError from dataclasses.replace() with unexpected keyword arguments indicates param_dict split failed; missing exit_reason values (all 'resolution') indicates exit_params not threaded to make_trade(); missing SL/TP columns in metrics CSV indicates run_strategy() not augmenting metrics dict
- **Redaction constraints:** No sensitive data — parameter grids and metric values are all numeric thresholds

## Integration Closure

- Upstream surfaces consumed: S01's `get_param_grid()` return values with stop_loss and take_profit keys; S02's `simulate_sl_tp_exit()` and `Trade.exit_reason` field
- New wiring introduced in this slice: optimize.py now splits param_dict and threads exit_params through run_strategy() to make_trade(); run_strategy() augments metrics dict with SL/TP values
- What remains before the milestone is truly usable end-to-end: S04 must add stop_loss, take_profit, and exit_reason columns to output CSV and format top 10 summary with explicit SL/TP values

## Tasks

- [x] **T01: Split parameter dict and thread exit params in optimize.py** `est:45m`
  - Why: optimize_strategy() must identify which param_dict keys are config fields vs exit params, split accordingly, and pass exit_params to run_strategy() so they reach make_trade()
  - Files: `src/analysis/optimize.py`
  - Do: In optimize_strategy(), after getting param_grid from strategy, introspect base_config dataclass using `dataclasses.fields(type(base_config))` to build set of valid config field names. Split each param_dict from Cartesian product into strategy_params (keys in config_fields) and exit_params (keys not in config_fields). Pass strategy_params to dataclasses.replace(). Pass exit_params.get('stop_loss') and exit_params.get('take_profit') to run_strategy() as keyword-only arguments. Update run_strategy() call signature: `run_strategy(config_label, strategy, markets, slippage=slippage, base_rate=base_rate, stop_loss=exit_params.get('stop_loss'), take_profit=exit_params.get('take_profit'))`.
  - Verify: `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` shows grid summary with stop_loss and take_profit dimensions and prints "Total combinations: 972" (or similar high count)
  - Done when: Dry-run completes without errors and grid summary explicitly lists stop_loss and take_profit ranges

- [x] **T02: Accept and thread SL/TP in run_strategy, augment metrics dict** `est:30m`
  - Why: run_strategy() must accept stop_loss and take_profit parameters, pass them to make_trade(), and augment metrics dict so SL/TP values appear in CSV output
  - Files: `src/analysis/backtest_strategies.py`
  - Do: Update run_strategy() signature to accept `stop_loss: float | None = None` and `take_profit: float | None = None` as keyword-only parameters after base_rate. Update make_trade() calls to pass these parameters: `make_trade(..., stop_loss=stop_loss, take_profit=take_profit)`. After compute_metrics() call, augment metrics dict before returning: `if stop_loss is not None: metrics['stop_loss'] = stop_loss` and `if take_profit is not None: metrics['take_profit'] = take_profit`.
  - Verify: `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` runs full backtest without errors; verify trades have exit_reason populated by loading a trade CSV and checking `exit_reason` column has mix of 'sl', 'tp', 'resolution' values
  - Done when: Full optimize run completes, at least one trade CSV exists, and exit_reason column shows non-uniform values (not all 'resolution')

## Files Likely Touched

- `src/analysis/optimize.py`
- `src/analysis/backtest_strategies.py`
