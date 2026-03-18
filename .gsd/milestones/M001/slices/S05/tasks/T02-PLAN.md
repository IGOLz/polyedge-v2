---
estimated_steps: 6
estimated_files: 3
---

# T02: Build parameter optimization script with grid-search CLI

**Slice:** S05 — Strategy template + parameter optimization
**Milestone:** M001

## Description

Create `analysis/optimize.py` — a grid-search parameter optimizer that systematically explores a strategy's config space and ranks results by backtest performance (R012). Also adds `get_param_grid()` to S1 and S2 config modules to define their search spaces. The optimizer reuses `backtest_strategies.run_strategy()` for evaluation and `engine.add_ranking_score()` + `engine.save_module_results()` for ranking and output.

**Relevant skills:** None required — pure Python, uses only existing infrastructure.

## Steps

1. Add `get_param_grid() -> dict[str, list]` to `src/shared/strategies/S1/config.py`:
   - Return a dict mapping config field names to lists of candidate values
   - Keep the grid small to avoid combinatorial explosion. S1 has 6 tunable params; pick 2-3 key ones with 3-4 values each
   - Recommended grid for S1:
     ```python
     def get_param_grid() -> dict[str, list]:
         return {
             "spike_threshold_up": [0.75, 0.80, 0.85],
             "reversion_reversal_pct": [0.08, 0.10, 0.12],
             "entry_price_threshold": [0.30, 0.35, 0.40],
         }
     ```
   - This gives 3×3×3 = 27 combinations — manageable

2. Add `get_param_grid() -> dict[str, list]` to `src/shared/strategies/S2/config.py`:
   - Recommended grid for S2:
     ```python
     def get_param_grid() -> dict[str, list]:
         return {
             "volatility_threshold": [0.03, 0.05, 0.07],
             "min_spread": [0.03, 0.05, 0.07],
             "base_deviation": [0.06, 0.08, 0.10],
         }
     ```
   - Also 27 combinations

3. Create `src/analysis/optimize.py` with the following structure:

   **Imports:** `argparse`, `itertools`, `importlib`, `sys`, `pandas`, plus from `analysis.backtest_strategies` import `run_strategy`, from `analysis.backtest.engine` import `add_ranking_score`, `save_module_results`, from `shared.strategies.registry` import `discover_strategies`.

   **Core function `optimize_strategy(strategy_id, markets, output_dir, dry_run=False)`:**
   - Discover strategies via `discover_strategies()`
   - Validate `strategy_id` exists and is not `'TEMPLATE'`
   - Dynamically import `get_param_grid` from `shared.strategies.{strategy_id}.config` using `importlib.import_module()`
   - If `get_param_grid` doesn't exist on the module, print a message and return
   - Get the grid dict, compute Cartesian product via `itertools.product(*grid.values())`
   - Print grid summary: param names, values, total combinations
   - If `dry_run`, print and return
   - For each param combination:
     - Build a config label like `S1_spike_threshold_up=0.75_reversion_reversal_pct=0.08_...`
     - Import the strategy's config class and `get_default_config()`
     - Create a new config by calling `get_default_config()` then overriding fields: use `dataclasses.replace(base_config, **param_dict)` — this is cleaner than constructor kwargs since it preserves strategy_id/strategy_name
     - Instantiate the strategy class with custom config
     - Call `run_strategy(config_label, strategy_instance, markets)` — note: `run_strategy` takes `strategy_id` as first arg (used as `config_id` in metrics)
     - Collect metrics dict
   - Build DataFrame from all metrics
   - Apply `add_ranking_score(df)` — works fine with 1+ rows
   - Sort by `ranking_score` descending
   - Print top 10 summary to stdout
   - Save results via `save_module_results(df, trades_by_config, f"optimize_{strategy_id}", output_dir)`

   **CLI (`main()` / `if __name__ == "__main__"`):**
   - `--strategy` (required): strategy ID to optimize
   - `--dry-run`: print grid and exit
   - `--output-dir`: results directory (default: `./results/optimization`)
   - `--assets`: comma-separated asset filter (passed to data_loader)
   - `--durations`: comma-separated duration filter
   - Load market data same way `backtest_strategies.main()` does: `data_loader.load_all_data()` + `data_loader.filter_markets()`
   - Call `optimize_strategy()`

   **Important constraints:**
   - Do NOT modify `backtest_strategies.py` or `engine.py` — import and call only
   - Use `dataclasses.replace()` for config overrides (cleaner than manual construction)
   - Skip strategies with no `get_param_grid()` (check with `hasattr`)
   - Skip TEMPLATE strategy explicitly
   - The `run_strategy()` function from `backtest_strategies.py` signature is: `run_strategy(strategy_id: str, strategy, markets: list[dict]) -> tuple[list[Trade], dict]` — the first arg becomes `config_id` in the metrics dict

4. Add `src/analysis/optimize.py` to be runnable as a module: the file should have `if __name__ == "__main__": main()` at the bottom.

5. Verify `get_param_grid()` works for both strategies:
   - `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S1.config import get_param_grid; g = get_param_grid(); assert isinstance(g, dict); assert len(g) > 0; print('S1 grid:', g)"`
   - `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S2.config import get_param_grid; g = get_param_grid(); assert isinstance(g, dict); assert len(g) > 0; print('S2 grid:', g)"`

6. Verify optimizer dry-run:
   - `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` — prints grid params, values, and combination count (27), exits 0
   - `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S2 --dry-run` — same for S2
   - Run regression scripts: `cd src && PYTHONPATH=. python3 scripts/parity_test.py`, `verify_s01.py`, `verify_s02.py`

## Observability Impact

- **New stdout signals:** Dry-run mode prints grid summary (param names, value lists, combination count) — useful for verifying search space before committing to a full run. Full run prints per-combination progress via `run_strategy()` output and a top-10 summary table at the end.
- **New inspection surface:** `results/optimization/` directory contains `Test_optimize_{strategy_id}_Results.csv` (all combos ranked), `optimize_{strategy_id}_Best_Configs.txt` (top 10 with sample trades), `optimize_{strategy_id}_Analysis.md` (distribution summary). All produced by existing `save_module_results()`.
- **Diagnostic commands for future agents:**
  - `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` — verify grid is correct without DB access.
  - `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid())"` — inspect a strategy's search space.
- **Failure visibility:** Missing `get_param_grid()` → printed message + clean exit (no traceback). Invalid strategy ID → `KeyError` from registry with available IDs listed. TEMPLATE strategy → explicit skip message.

## Must-Haves

- [ ] `S1/config.py` has `get_param_grid()` returning a non-empty dict of param → value lists
- [ ] `S2/config.py` has `get_param_grid()` returning a non-empty dict of param → value lists
- [ ] `analysis/optimize.py` exists and is runnable as `python -m analysis.optimize`
- [ ] `--dry-run` flag prints grid summary and exits without loading market data
- [ ] `--strategy` flag selects a single strategy to optimize
- [ ] Optimizer skips TEMPLATE and strategies without `get_param_grid()`
- [ ] Optimizer uses `dataclasses.replace()` for config overrides
- [ ] Optimizer calls `run_strategy()` from `backtest_strategies.py` (no modification to that file)
- [ ] Optimizer calls `add_ranking_score()` and `save_module_results()` from engine (no modification)
- [ ] All existing verification scripts pass (no regressions)

## Verification

- `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` — exit code 0, prints 27 combinations
- `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S2 --dry-run` — exit code 0, prints 27 combinations
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid())"` — non-empty dict
- `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — exit code 0
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — exit code 0
- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — exit code 0

## Inputs

- `src/shared/strategies/S1/config.py` — S1Config dataclass to add get_param_grid() to; fields: spike_detection_window_seconds, spike_threshold_up, spike_threshold_down, reversion_reversal_pct, min_reversion_ticks, entry_price_threshold
- `src/shared/strategies/S2/config.py` — S2Config dataclass to add get_param_grid() to; fields: eval_second, eval_window, volatility_window_seconds, volatility_threshold, min_spread, max_spread, base_deviation
- `src/analysis/backtest_strategies.py` — `run_strategy(strategy_id, strategy, markets)` function (DO NOT MODIFY)
- `src/analysis/backtest/engine.py` — `add_ranking_score(df)`, `save_module_results(df, trades, name, dir)` functions (DO NOT MODIFY)
- `src/shared/strategies/registry.py` — `discover_strategies()` returns dict of strategy_id → strategy class

## Expected Output

- `src/shared/strategies/S1/config.py` — modified: added `get_param_grid()` function
- `src/shared/strategies/S2/config.py` — modified: added `get_param_grid()` function
- `src/analysis/optimize.py` — new: grid-search optimizer with CLI (--strategy, --dry-run, --output-dir, --assets, --durations)
