# S02: Analysis adapter — backtest through shared strategies — Research

**Date:** 2026-03-18

## Summary

This slice wires the shared strategy framework (from S01) into the existing analysis backtest pipeline. The work is straightforward: the existing `data_loader.load_all_data()` already produces numpy arrays indexed by elapsed second — the exact format `MarketSnapshot.prices` expects. The adapter needs to (1) wrap each market dict into a `MarketSnapshot`, (2) call `strategy.evaluate(snapshot)` to get a `Signal | None`, (3) convert the Signal into a `Trade` using the existing `engine.make_trade()`, and (4) feed trades to `engine.compute_metrics()` for performance reporting.

The entire adapter is a single new file (`analysis/backtest_strategies.py`) with a `run_strategy()` function and a CLI entry point. It imports from two existing modules (`data_loader`, `engine`) and from the shared strategy framework — no modifications to any existing file. The data conversion from market dict to `MarketSnapshot` is a ~10-line function. The only non-trivial mapping is extracting `second_entered` from `Signal.signal_data` (S1 puts `reversion_second` there), which requires a convention: strategies must include an entry-second in their signal_data for the backtest adapter to record when the trade was entered.

## Recommendation

Build one new file `src/analysis/backtest_strategies.py` that reuses `data_loader.load_all_data()` for data loading and `engine.make_trade()` / `engine.compute_metrics()` / `engine.save_module_results()` for metrics and output. The adapter function converts market dicts → `MarketSnapshot`, calls `strategy.evaluate()`, converts `Signal` → `Trade`. CLI uses argparse with `--strategy` (specific ID or all) and `--output-dir` flags, matching the existing analysis CLI patterns. Runnable as `python3 -m analysis.backtest_strategies`.

Do NOT modify any existing analysis files. Do NOT rewrite the data loading or metrics pipeline. The value of this slice is proving the shared strategy produces identical results when plugged into the existing backtest infrastructure.

## Implementation Landscape

### Key Files

- `src/analysis/backtest/data_loader.py` (existing, read-only) — `load_all_data()` returns `list[dict]` where each dict has `ticks` (numpy ndarray indexed by elapsed second, NaN for missing), `market_id`, `market_type`, `total_seconds`, `asset`, `duration_minutes`, `started_at`, `ended_at`, `final_outcome`, `hour`. Also provides `filter_markets(markets, assets, durations)` for subsetting.
- `src/analysis/backtest/engine.py` (existing, read-only) — `make_trade(market, second_entered, entry_price, direction)` returns `Trade`. `compute_metrics(trades, config_id)` returns metrics dict. `add_ranking_score(df)` adds composite score. `save_module_results(df, trades_by_config, module_name, module_dir)` saves CSV + markdown + best configs.
- `src/analysis/backtest_strategies.py` (NEW) — The adapter. Imports `data_loader.load_all_data`, `engine.make_trade`, `engine.compute_metrics`, `engine.save_module_results`, and `shared.strategies.{discover_strategies, get_strategy, MarketSnapshot}`. CLI entry point for `python3 -m analysis.backtest_strategies`.
- `src/shared/strategies/base.py` (existing, from S01) — `MarketSnapshot` (market_id, market_type, prices, total_seconds, elapsed_seconds, metadata), `Signal` (direction, strategy_name, entry_price, signal_data, ...), `BaseStrategy`.
- `src/shared/strategies/registry.py` (existing, from S01) — `discover_strategies()`, `get_strategy(id)`.
- `src/shared/strategies/S1/strategy.py` (existing, from S01) — `S1Strategy.evaluate(snapshot) -> Signal | None`. Signal's `signal_data` includes `reversion_second` (the second the entry occurs).
- `src/scripts/verify_s02.py` (NEW) — Contract verification script, following S01's `verify_s01.py` pattern.

### Conversion Details

**Market dict → MarketSnapshot mapping:**
```python
def market_to_snapshot(market: dict) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market['market_id'],
        market_type=market['market_type'],
        prices=market['ticks'],           # already numpy ndarray, seconds-indexed
        total_seconds=market['total_seconds'],
        elapsed_seconds=market['total_seconds'],  # backtest: full market available
        metadata={
            'asset': market['asset'],
            'hour': market['hour'],
            'started_at': market['started_at'],
            'final_outcome': market['final_outcome'],
            'duration_minutes': market['duration_minutes'],
        },
    )
```

**Signal → Trade mapping:**
```python
signal = strategy.evaluate(snapshot)
if signal is not None:
    # Extract entry second from signal_data (strategy-specific key)
    second_entered = signal.signal_data.get('reversion_second', 0)
    trade = make_trade(market, second_entered, signal.entry_price, signal.direction)
```

**CLI interface:**
```
python3 -m analysis.backtest_strategies                    # run all discovered strategies
python3 -m analysis.backtest_strategies --strategy S1      # run specific strategy
python3 -m analysis.backtest_strategies --output-dir ./results  # custom output
```

### Build Order

1. **T01: Create `analysis/backtest_strategies.py` with adapter + CLI** — This is the entire slice. One file with: `market_to_snapshot()` conversion, `run_strategy(strategy, markets)` that loops markets → snapshot → evaluate → trade → metrics, and `main()` with argparse CLI. Uses `data_loader.load_all_data()` for data, `engine.make_trade()` / `compute_metrics()` / `save_module_results()` for reporting.

2. **T02: Create `scripts/verify_s02.py` contract verification** — Verifies: (a) the module is importable, (b) `market_to_snapshot()` produces valid MarketSnapshot from a synthetic market dict, (c) the full pipeline runs on synthetic data (market dict → snapshot → strategy.evaluate → Signal → Trade → metrics), (d) CLI entry point exists and parses args. This does NOT require a database — it uses synthetic market dicts with crafted numpy arrays.

### Verification Approach

**Contract verification (no DB needed):**
```bash
cd src && PYTHONPATH=. python3 scripts/verify_s02.py
```
Checks:
- `from analysis.backtest_strategies import market_to_snapshot, run_strategy` works
- `market_to_snapshot(synthetic_market_dict)` returns valid MarketSnapshot with correct prices shape
- Synthetic market with known spike+reversion data → `run_strategy()` → produces at least one Trade with correct direction/entry_price
- `compute_metrics()` on the trades returns a dict with expected keys
- CLI `--help` flag works without DB

**Integration verification (requires DB):**
```bash
cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1
```
Should load markets from DB, run S1 against them, print summary stats, and save results to output dir.

**Cross-check with original module_3:**
- Run original `module_3_mean_reversion.py` on the same data and compare that S1 via shared adapter produces trades on the same markets (not necessarily identical counts due to config differences, but directionally consistent).

## Constraints

- `PYTHONPATH` must include `src/` — the shared strategy registry uses `importlib.import_module('shared.strategies.{id}.strategy')` which requires this (fragile point from S01).
- `data_loader.load_all_data()` uses asyncpg internally (`asyncio.run()`), so the adapter must not already be inside an async event loop. This is fine — analysis is sync-only.
- The adapter must not modify any existing analysis file. It imports from `analysis.backtest.data_loader` and `analysis.backtest.engine` only.
- Strategies provide entry-second in `signal_data` under strategy-specific keys (S1 uses `reversion_second`). The adapter needs a convention to extract this — either a well-known key like `entry_second`, or the adapter reads it from the strategy-specific key. Recommendation: read `signal_data.get('reversion_second', 0)` for S1, and define a convention that strategies should include `entry_second` in signal_data going forward.

## Common Pitfalls

- **signal_data key mismatch** — S1's `signal_data` uses `reversion_second` not `entry_second`. The adapter must use the actual key the strategy produces. Don't invent a key that doesn't exist in the Signal — read S1's code to confirm the field name. If a strategy doesn't provide an entry second, default to 0 (start of market).
- **elapsed_seconds for backtest** — In backtesting, the full market data is available, so `elapsed_seconds` should equal `total_seconds`. In live trading (S03), it'll be the current time. Don't accidentally set it to 0 or leave it unset.
- **Import path confusion** — `data_loader` and `engine` are in `analysis.backtest.*`, not `analysis.*`. The new file at `analysis/backtest_strategies.py` imports from `analysis.backtest.data_loader` and `analysis.backtest.engine`.
