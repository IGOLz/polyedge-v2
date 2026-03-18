---
estimated_steps: 5
estimated_files: 1
---

# T01: Split parameter dict and thread exit params in optimize.py

**Slice:** S03 — Grid Search Orchestrator
**Milestone:** M004

## Description

Modify optimize_strategy() to introspect the strategy config dataclass and identify which param_dict keys are valid config fields versus exit parameters (stop_loss, take_profit). Split each parameter combination dict into strategy_params (passed to dataclasses.replace) and exit_params (passed as keyword arguments to run_strategy). This enables the grid search to correctly handle SL/TP parameters that are NOT part of the strategy config dataclass.

The current dry-run already works and shows 972 combinations for S1 including SL/TP dimensions. This task wires the split logic so that when the full backtest runs, exit_params reach make_trade() correctly.

## Steps

1. Open `src/analysis/optimize.py` and locate `optimize_strategy()` function
2. After line where `param_grid = strategy.get_param_grid()` is called, add introspection of base_config dataclass: `config_fields = {f.name for f in dataclasses.fields(type(base_config))}`
3. In the loop over `param_combinations`, split each `param_dict` into two dicts:
   - `strategy_params = {k: v for k, v in param_dict.items() if k in config_fields}`
   - `exit_params = {k: v for k, v in param_dict.items() if k not in config_fields}`
4. Update `dataclasses.replace()` call to use `strategy_params` instead of full `param_dict`: `custom_config = dataclasses.replace(base_config, **strategy_params)`
5. Update `run_strategy()` call to pass exit_params as keyword arguments: `run_strategy(config_label, strategy, markets, slippage=slippage, base_rate=base_rate, stop_loss=exit_params.get('stop_loss'), take_profit=exit_params.get('take_profit'))`
6. Add `import dataclasses` at top of file if not already present

## Must-Haves

- [ ] config_fields set created from base_config dataclass introspection
- [ ] param_dict split into strategy_params and exit_params in loop
- [ ] dataclasses.replace() uses strategy_params only
- [ ] run_strategy() receives stop_loss and take_profit as keyword arguments from exit_params dict
- [ ] Dry-run verification passes showing grid includes SL/TP dimensions

## Observability Impact

- **Signals added:** Dry-run output now explicitly lists stop_loss and take_profit as grid dimensions (previously these were silently included in param_dict but not validated)
- **Inspection method:** Check dry-run output for "stop_loss: [...]" and "take_profit: [...]" lines; verify dataclasses.replace() calls succeed without TypeError
- **Failure state visible:** TypeError with message "unexpected keyword argument 'stop_loss'" indicates param_dict split not working; missing SL/TP in dry-run output indicates get_param_grid() not returning exit params
- **Changed observability from baseline:** No new log statements added — this task changes internal parameter routing only. Observability comes from dry-run output (already present) and absence of runtime errors.

## Verification

- `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` completes without errors
- Output includes "stop_loss: [0.35, 0.4, 0.45]" and "take_profit: [0.65, 0.7, 0.75]" in grid summary
- Output shows "Total combinations: 972" (or similar high count including SL/TP dimensions)
- No TypeError from dataclasses.replace() about unexpected keyword arguments

## Inputs

- `src/analysis/optimize.py` — Current implementation generates Cartesian product but passes full param_dict to dataclasses.replace(), which will fail when param_dict includes stop_loss/take_profit keys that aren't config fields
- S01 deliverable: All strategies have get_param_grid() returning dicts with stop_loss and take_profit keys (648-1728 combinations per strategy)
- S02 deliverable: make_trade() accepts stop_loss and take_profit as keyword-only parameters

## Expected Output

- `src/analysis/optimize.py` — Updated optimize_strategy() function that introspects config dataclass, splits param_dict correctly, and threads exit_params through run_strategy() call. Dry-run verification proves grid generation works with SL/TP dimensions.
