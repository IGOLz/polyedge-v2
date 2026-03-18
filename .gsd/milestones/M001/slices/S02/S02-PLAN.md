# S02: Analysis adapter — backtest through shared strategies

**Goal:** The existing analysis backtest engine can run shared strategies from the registry against historical market data, producing standard backtest metrics and reports.
**Demo:** `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1` loads markets from DB, runs S1 via the shared framework, and outputs performance metrics + CSV/markdown reports using the existing engine.

## Must-Haves

- `analysis/backtest_strategies.py` exists with `market_to_snapshot()`, `run_strategy()`, and CLI entry point
- `market_to_snapshot()` converts the data_loader market dict to a valid `MarketSnapshot` (prices=ticks ndarray, elapsed_seconds=total_seconds)
- Signal → Trade conversion extracts `reversion_second` from `signal_data` as the entry second
- CLI supports `--strategy <ID>` (single strategy) and no flag (all discovered strategies)
- CLI supports `--output-dir` for custom results directory
- Uses `engine.make_trade()`, `engine.compute_metrics()`, `engine.add_ranking_score()`, `engine.save_module_results()` for reporting — no reimplementation
- No modifications to any existing file in `analysis/`, `trading/`, or `core/`

## Proof Level

- This slice proves: integration (shared strategies produce backtest results through existing engine)
- Real runtime required: yes (DB for full integration; synthetic data for contract verification)
- Human/UAT required: no

## Verification

- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — contract verification (18+ checks, no DB needed): importability, market_to_snapshot conversion, Signal→Trade pipeline on synthetic data, CLI --help, metrics computation
- `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1` — integration verification (requires DB): loads real markets, runs S1, saves results
- `cd src && PYTHONPATH=. python3 -c "from analysis.backtest_strategies import run_strategy; from shared.strategies import get_strategy; s = get_strategy('S1'); trades, metrics = run_strategy('S1', s, []); assert metrics['total_bets'] == 0; print('empty-market diagnostic OK')"` — failure-path check: zero markets produces empty metrics without error

## Observability / Diagnostics

- **Structured progress output:** `run_strategy()` prints strategy ID, market count, and trade count to stdout for each strategy evaluated, enabling progress tracking and post-hoc inspection.
- **CLI `--help`:** Verifiable entry point — `python3 -m analysis.backtest_strategies --help` confirms the module loads without errors.
- **Metrics dict surface:** Every strategy run produces a metrics dict with `total_bets`, `win_rate_pct`, `total_pnl`, and 17 other keys. Non-zero `total_bets` confirms the Signal→Trade pipeline is live.
- **Saved artifacts:** `save_module_results()` writes CSV, best-configs text, and analysis markdown under `--output-dir`. Presence and content of these files is the primary inspection surface for backtest results.
- **Failure visibility:** If a strategy raises during `evaluate()`, the exception propagates with full traceback (no swallowing). If zero trades are generated, `compute_metrics` returns an `_empty_metrics` dict with `total_bets=0` — visible in the saved CSV.
- **No secrets or PII:** Market data is public price feeds. No credentials are embedded or logged.

## Integration Closure

- Upstream surfaces consumed: `shared/strategies/{base, registry, S1}` from S01; `analysis/backtest/{data_loader, engine}` existing code (read-only)
- New wiring introduced in this slice: `analysis/backtest_strategies.py` — new entry point composing shared strategies with existing backtest infrastructure
- What remains before the milestone is truly usable end-to-end: S03 (trading adapter), S04 (parity verification), S05 (template + optimization)

## Tasks

- [x] **T01: Create analysis backtest adapter with market conversion, strategy runner, and CLI** `est:30m`
  - Why: This is the entire slice deliverable — one new file that bridges shared strategies into the existing backtest pipeline. No existing files are modified.
  - Files: `src/analysis/backtest_strategies.py`
  - Do: Create `backtest_strategies.py` with three components: (1) `market_to_snapshot(market_dict) -> MarketSnapshot` that maps data_loader's market dict format to a MarketSnapshot (prices=market['ticks'], elapsed_seconds=total_seconds, metadata includes asset/hour/started_at/final_outcome/duration_minutes), (2) `run_strategy(strategy, markets) -> (list[Trade], metrics_dict)` that loops markets → snapshot → evaluate → Signal → Trade via `engine.make_trade()`, then computes metrics via `engine.compute_metrics()`, (3) `main()` with argparse CLI: `--strategy` flag for specific ID, `--output-dir` for results path, `--assets` and `--durations` for market filtering. CLI loads data with `data_loader.load_all_data()`, discovers/selects strategies from registry, runs each, builds DataFrame with `add_ranking_score()`, saves with `save_module_results()`. The Signal → Trade bridge uses `signal.signal_data.get('reversion_second', 0)` for second_entered. Import from `analysis.backtest.data_loader` and `analysis.backtest.engine` (not `analysis.*`). Module must be runnable as `python3 -m analysis.backtest_strategies`.
  - Verify: `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --help` shows usage without errors
  - Done when: `backtest_strategies.py` is importable, `market_to_snapshot` and `run_strategy` are callable, CLI `--help` works

- [x] **T02: Create contract verification script for S02** `est:25m`
  - Why: Proves the adapter pipeline works end-to-end on synthetic data without requiring a database. Catches import errors, conversion bugs, and Signal→Trade mapping issues. Following the verify_s01.py pattern established in S01.
  - Files: `src/scripts/verify_s02.py`
  - Do: Create `verify_s02.py` modeled on `scripts/verify_s01.py` (read it first for the pattern). Checks: (1) import `market_to_snapshot`, `run_strategy` from `analysis.backtest_strategies`, (2) import `MarketSnapshot`, `Signal` from `shared.strategies`, (3) build a synthetic market dict matching data_loader's output format (market_id, market_type='BTC_5m', asset='BTC', ticks=numpy array with spike+reversion pattern, total_seconds=300, duration_minutes=5, started_at=datetime, ended_at=datetime, final_outcome='Down', hour=12), (4) verify `market_to_snapshot()` returns MarketSnapshot with correct prices shape and metadata, (5) verify `MarketSnapshot.elapsed_seconds == total_seconds` (backtest convention), (6) get S1 strategy via `get_strategy('S1')`, call evaluate on the snapshot, assert Signal is returned with direction and reversion_second in signal_data, (7) verify `engine.make_trade()` accepts the market dict + Signal-derived args and returns a Trade, (8) verify `engine.compute_metrics()` returns dict with expected keys (total_bets, win_rate_pct, total_pnl, etc.), (9) verify CLI entry point exists by importing `main` from `analysis.backtest_strategies`, (10) verify no imports from `trading.*` or `core.*` in the adapter module. Use the S1 calibration knowledge from S01: test prices must produce entry_price ≤ 0.35 (S1's threshold). Print pass/fail per check with summary. Exit 0 on all pass, 1 on any fail.
  - Verify: `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` exits 0 with all checks passing
  - Done when: All checks pass, exit code 0, no DB required

## Files Likely Touched

- `src/analysis/backtest_strategies.py` (NEW)
- `src/scripts/verify_s02.py` (NEW)
