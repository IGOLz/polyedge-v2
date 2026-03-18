---
id: T01
parent: S02
milestone: M001
provides:
  - analysis.backtest_strategies module with market_to_snapshot(), run_strategy(), and CLI entry point
  - Bridge between shared strategy framework and existing analysis backtest engine
key_files:
  - src/analysis/backtest_strategies.py
key_decisions:
  - Copied analysis/backtest/{engine,data_loader} and shared/config.py into worktree as read-only dependencies (untracked in main repo, needed for import chain)
patterns_established:
  - Adapter pattern: new module composes upstream interfaces (shared.strategies + analysis.backtest.engine) without modifying either
  - Signal→Trade bridge extracts entry_second from signal_data via .get('reversion_second', 0) with fallback
observability_surfaces:
  - stdout progress: "[{strategy_id}] Evaluating {N} markets → {M} trades" per strategy
  - CLI --help for module integrity check
  - Saved CSV/markdown artifacts in --output-dir for post-hoc inspection
  - Zero-trade strategies produce total_bets=0 in metrics (visible in output)
duration: 12m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T01: Create analysis backtest adapter with market conversion, strategy runner, and CLI

**Created analysis/backtest_strategies.py bridging shared strategies into the analysis backtest engine with market conversion, strategy runner, and argparse CLI**

## What Happened

Created `src/analysis/backtest_strategies.py` (~160 lines) with three components:

1. **`market_to_snapshot(market: dict) -> MarketSnapshot`** — converts data_loader market dicts to MarketSnapshot objects. Maps `ticks` → `prices`, sets `elapsed_seconds = total_seconds` (backtest convention), and populates metadata with asset/hour/started_at/final_outcome/duration_minutes.

2. **`run_strategy(strategy_id, strategy, markets) -> (list[Trade], dict)`** — loops markets, converts to snapshots, calls `strategy.evaluate()`, extracts `reversion_second` from Signal's `signal_data` for the entry second, and creates Trade objects via `engine.make_trade()`. Computes metrics via `engine.compute_metrics()`. Prints progress to stdout.

3. **`main()` with argparse CLI** — supports `--strategy/-s`, `--output-dir/-o`, `--assets`, `--durations` flags. Loads data via `data_loader.load_all_data()`, discovers/selects strategies, runs each, builds DataFrame with `add_ranking_score()`, saves with `save_module_results()`, and prints summary.

Also copied `analysis/backtest/{engine.py, data_loader.py, __init__.py}`, `analysis/__init__.py`, and `shared/config.py` into the worktree as read-only dependencies needed for the import chain. These files are untracked in the main repo but required for `data_loader` to import without errors.

## Verification

- Import check: `from analysis.backtest_strategies import market_to_snapshot, run_strategy, main` succeeds
- CLI `--help` displays usage with all four flags
- Empty-market diagnostic: `run_strategy('S1', strategy, [])` returns `total_bets=0` without error
- End-to-end Signal→Trade pipeline: synthetic spike market produces 1 trade with correct direction, entry_price, second_entered, and PnL
- No `trading.*` or `core.*` imports verified via AST inspection

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `PYTHONPATH=. python3 -c "from analysis.backtest_strategies import market_to_snapshot, run_strategy, main; print('OK')"` | 0 | ✅ pass | 0.5s |
| 2 | `PYTHONPATH=. python3 -m analysis.backtest_strategies --help` | 0 | ✅ pass | 0.5s |
| 3 | `PYTHONPATH=. python3 -c "...run_strategy('S1', s, []); assert metrics['total_bets'] == 0..."` | 0 | ✅ pass | 0.5s |
| 4 | `PYTHONPATH=. python3 scripts/verify_s02.py` | — | ⏳ pending (T02 deliverable) | — |
| 5 | `PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1` | — | ⏳ pending (requires DB) | — |

## Diagnostics

- **Module integrity:** `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --help` — confirms clean import chain
- **Progress signal:** Each strategy prints `[{id}] Evaluating N markets → M trades` to stdout
- **Result artifacts:** After a run, check `--output-dir` for `Test_shared_strategies_Results.csv`, `shared_strategies_Best_Configs.txt`, and `shared_strategies_Analysis.md`
- **Failure state:** Strategy evaluation exceptions propagate with full tracebacks. Zero-trade results produce `total_bets=0` rows in CSV.

## Deviations

- Copied `analysis/backtest/`, `analysis/__init__.py`, and `shared/config.py` into the worktree. These files exist on disk in the main repo but are untracked by git, so they weren't present in the milestone branch. Required for the `data_loader` → `shared.config` import chain to resolve.

## Known Issues

- None

## Files Created/Modified

- `src/analysis/backtest_strategies.py` — NEW: adapter module with market_to_snapshot(), run_strategy(), main(), and __main__ guard
- `src/analysis/__init__.py` — COPIED from main repo (read-only dependency)
- `src/analysis/backtest/__init__.py` — COPIED from main repo (read-only dependency)
- `src/analysis/backtest/engine.py` — COPIED from main repo (read-only dependency)
- `src/analysis/backtest/data_loader.py` — COPIED from main repo (read-only dependency)
- `src/shared/config.py` — COPIED from main repo (read-only dependency for data_loader import chain)
- `.gsd/milestones/M001/slices/S02/S02-PLAN.md` — Added Observability/Diagnostics section, failure-path verification check, marked T01 done
- `.gsd/milestones/M001/slices/S02/tasks/T01-PLAN.md` — Added Observability Impact section
