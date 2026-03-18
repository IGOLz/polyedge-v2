---
estimated_steps: 5
estimated_files: 1
---

# T01: Create analysis backtest adapter with market conversion, strategy runner, and CLI

**Slice:** S02 — Analysis adapter — backtest through shared strategies
**Milestone:** M001

## Description

Create a single new file `src/analysis/backtest_strategies.py` that bridges the shared strategy framework (from S01) into the existing analysis backtest infrastructure. This adapter converts data_loader market dicts into `MarketSnapshot` objects, evaluates strategies via the shared registry, converts returned `Signal` objects into `Trade` objects using the existing engine, and computes/saves performance metrics. The module is runnable as `python3 -m analysis.backtest_strategies` with CLI flags for strategy selection, output directory, and market filtering.

No existing files are modified. The adapter imports from `analysis.backtest.data_loader` (for `load_all_data`, `filter_markets`) and `analysis.backtest.engine` (for `make_trade`, `compute_metrics`, `add_ranking_score`, `save_module_results`), plus `shared.strategies` (for `discover_strategies`, `get_strategy`, `MarketSnapshot`).

## Steps

1. **Create `src/analysis/backtest_strategies.py`** with module docstring explaining its purpose: bridge between shared strategies and the analysis backtest engine.

2. **Implement `market_to_snapshot(market: dict) -> MarketSnapshot`** — the conversion function:
   ```python
   from shared.strategies import MarketSnapshot
   
   def market_to_snapshot(market: dict) -> MarketSnapshot:
       return MarketSnapshot(
           market_id=market['market_id'],
           market_type=market['market_type'],
           prices=market['ticks'],           # numpy ndarray, seconds-indexed, NaN for missing
           total_seconds=market['total_seconds'],
           elapsed_seconds=market['total_seconds'],  # backtest: full market data available
           metadata={
               'asset': market['asset'],
               'hour': market['hour'],
               'started_at': market['started_at'],
               'final_outcome': market['final_outcome'],
               'duration_minutes': market['duration_minutes'],
           },
       )
   ```

3. **Implement `run_strategy(strategy_id, strategy, markets) -> tuple[list[Trade], dict]`** — runs one strategy against all markets:
   - Loop over each market dict
   - Convert to MarketSnapshot via `market_to_snapshot()`
   - Call `strategy.evaluate(snapshot)` — returns `Signal | None`
   - If Signal returned: extract `second_entered = signal.signal_data.get('reversion_second', 0)` and create a Trade via `engine.make_trade(market, second_entered, signal.entry_price, signal.direction)`
   - Collect all trades, then call `engine.compute_metrics(trades, config_id=strategy_id)`
   - Return `(trades, metrics)`
   - Print progress: strategy ID, number of markets, number of trades generated

4. **Implement `main()` with argparse CLI**:
   - `--strategy` / `-s`: run only this strategy ID (optional; if omitted, run all discovered strategies)
   - `--output-dir` / `-o`: directory for results (default: `./results/shared_strategies`)
   - `--assets`: comma-separated asset filter (optional, passed to `filter_markets`)
   - `--durations`: comma-separated duration filter in minutes (optional, passed to `filter_markets`)
   - Load data: `data_loader.load_all_data()` → optionally `data_loader.filter_markets()`
   - Discover strategies: `discover_strategies()` or `get_strategy(args.strategy)` for single
   - For each strategy: call `run_strategy()`, collect results
   - Build pandas DataFrame from all metrics dicts
   - Apply `engine.add_ranking_score(df)`
   - Save via `engine.save_module_results(df, trades_by_config, module_name, output_dir)`
   - Print summary to stdout

5. **Add `if __name__ == '__main__': main()` guard** so the module works with `python3 -m analysis.backtest_strategies`.

**Critical constraints:**
- Import `data_loader` and `engine` from `analysis.backtest`, not `analysis` (they're in the `backtest` subpackage)
- Signal's `signal_data` uses `reversion_second` key (S1-specific). Use `.get('reversion_second', 0)` for S1. Going forward, strategies should standardize on `entry_second`, but for now read what S1 actually produces.
- `elapsed_seconds` must equal `total_seconds` in backtest mode (full market data available). Do NOT set to 0.
- `PYTHONPATH` must include `src/` for imports to work — this is an environment constraint, not something the code controls.
- Use `python3` (not `python`) — only `python3` is available on this system.

## Must-Haves

- [ ] `market_to_snapshot()` correctly maps all market dict fields to MarketSnapshot (prices=ticks, elapsed_seconds=total_seconds, metadata includes asset/hour/started_at/final_outcome/duration_minutes)
- [ ] `run_strategy()` loops markets, evaluates strategy, converts Signal→Trade via engine.make_trade(), computes metrics
- [ ] CLI supports `--strategy`, `--output-dir`, `--assets`, `--durations` flags
- [ ] Module is runnable as `python3 -m analysis.backtest_strategies`
- [ ] No imports from `trading.*` or `core.*`; no modifications to existing files

## Verification

- `cd src && PYTHONPATH=. python3 -c "from analysis.backtest_strategies import market_to_snapshot, run_strategy, main; print('OK')"` — imports work
- `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --help` — CLI help text displays without errors

## Inputs

- `src/shared/strategies/base.py` — MarketSnapshot, Signal, BaseStrategy (from S01)
- `src/shared/strategies/registry.py` — discover_strategies(), get_strategy() (from S01)
- `src/shared/strategies/S1/strategy.py` — S1Strategy with evaluate() that returns Signal with `reversion_second` in signal_data (from S01)
- `src/analysis/backtest/data_loader.py` — `load_all_data()` returns list[dict] with keys: market_id, market_type, asset, duration_minutes, total_seconds, started_at, ended_at, final_outcome, hour, ticks (numpy ndarray). Also `filter_markets(markets, assets=None, durations=None)`.
- `src/analysis/backtest/engine.py` — `make_trade(market, second_entered, entry_price, direction)` → Trade. `compute_metrics(trades, config_id)` → dict. `add_ranking_score(df)` → df. `save_module_results(results_df, trades_by_config, module_name, module_dir)` saves CSV+markdown.

## Observability Impact

- **New stdout signals:** `run_strategy()` prints `"[{strategy_id}] Evaluating {N} markets → {M} trades"` per strategy. This is the primary runtime progress signal.
- **Inspection surface:** After a run, inspect `--output-dir` for CSV results (`Test_*_Results.csv`), best configs text, and analysis markdown. These files are the persistent diagnostic artifact.
- **Failure state:** Zero-trade strategies produce `total_bets=0` in metrics — visible in CSV output row. Strategy evaluation exceptions propagate as full tracebacks to stderr.
- **CLI introspection:** `python3 -m analysis.backtest_strategies --help` lists all flags and confirms module integrity without running any strategy.

## Expected Output

- `src/analysis/backtest_strategies.py` — New file (~120-150 lines) with `market_to_snapshot()`, `run_strategy()`, `main()`, and `__main__` guard. Fully importable, CLI functional.
