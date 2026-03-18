---
id: T01
parent: S03
milestone: M001
provides:
  - trading/strategy_adapter.py with ticks_to_snapshot() and evaluate_strategies()
  - Adapter bridging shared strategy framework into trading bot evaluation loop
key_files:
  - src/trading/strategy_adapter.py
key_decisions:
  - Symlinked existing trading modules from main repo into worktree for import resolution (worktree only has new files in git)
patterns_established:
  - Trading adapter follows same composition pattern as S02 analysis adapter (D008) — new module composes shared.strategies + existing trading infrastructure without modifying either
  - Profitability thesis built dynamically from signal_data context keys
observability_surfaces:
  - "[ADAPTER] N signal(s) for MARKET_ID" log line on signal generation
  - "[ADAPTER] skipping/already traded/no signals" debug_log lines for each guard path
  - Strategy evaluation exceptions caught per-strategy with debug_log, loop continues
duration: 15m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T01: Build trading strategy adapter module

**Created `src/trading/strategy_adapter.py` — adapter converting live ticks to MarketSnapshot, running shared strategies via registry, and populating all executor-required Signal fields**

## What Happened

Built `trading/strategy_adapter.py` following the composition pattern from S02's `analysis/backtest_strategies.py` (D008). The module exports three functions:

1. **`ticks_to_snapshot(market, ticks)`** — converts `MarketInfo` + `list[Tick]` into `MarketSnapshot` with numpy array indexed by elapsed second (NaN for missing), `elapsed_seconds` reflecting real wall-clock time (live context difference from S02's backtest convention where `elapsed == total`).

2. **`_populate_execution_fields(signal, market, snapshot, balance)`** — fills all 4 `locked_*` fields and 12 executor-required `signal_data` keys using `calculate_dynamic_bet_size()` and `calculate_shares()` from `trading.strategies`. Returns None if bet exceeds `max_single_trade_pct` risk guard.

3. **`evaluate_strategies(market, ticks)`** — async drop-in replacement for `trading.strategies.evaluate_strategies`. Guards: empty ticks (<2), balance failure (≤0), already-traded per strategy, bet-too-large. Iterates shared registry via `discover_strategies()` + `get_strategy()`, calls `strategy.evaluate(snapshot)` synchronously (D001), populates execution fields, returns `list[Signal]`.

Symlinked existing trading modules (`balance.py`, `db.py`, `constants.py`, `strategies.py`, `utils.py`, etc.) and `shared/db.py` from the main repo into the worktree so the import chain resolves. Only `strategy_adapter.py` is a new real file; everything else is symlinks for development context.

## Verification

- AST parse confirms `evaluate_strategies` is async, `ticks_to_snapshot` is sync, and `_populate_execution_fields` exists
- Import with mocked external deps (`py_clob_client`, `trading.config`, `shared.db`) succeeds; `inspect.iscoroutinefunction(evaluate_strategies)` returns True
- Module isolation: no imports from `analysis.*` or `core.*`
- Functional test: `ticks_to_snapshot()` produces correct numpy array with NaN for missing seconds, correct values for present seconds, `elapsed_seconds < total_seconds` in live context
- Functional test: `_populate_execution_fields()` populates all 4 `locked_*` fields and all 12 executor-required `signal_data` keys
- Bet-too-large guard returns None when `actual_cost > balance * max_single_trade_pct`
- No existing files modified (only untracked files in `git status`)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | AST export/async check | 0 | ✅ pass | <1s |
| 2 | Import with mocked deps + inspect.iscoroutinefunction | 0 | ✅ pass | <1s |
| 3 | Module isolation (no analysis/core imports) | 0 | ✅ pass | <1s |
| 4 | ticks_to_snapshot functional test (NaN, values, elapsed<total) | 0 | ✅ pass | <1s |
| 5 | _populate_execution_fields (locked_* + signal_data keys) | 0 | ✅ pass | <1s |
| 6 | Bet-too-large guard returns None | 0 | ✅ pass | <1s |
| 7 | git status — no existing files modified | 0 | ✅ pass | <1s |
| 8 | `scripts/verify_s03.py` (slice-level) | — | ⏳ pending T02 | — |

## Diagnostics

- **Import test:** `cd src && PYTHONPATH=. python3 -c "import sys; from unittest.mock import MagicMock; [sys.modules.update({k: MagicMock()}) for k in ['py_clob_client','py_clob_client.client','py_clob_client.clob_types','trading.config','shared.db','colorama']]; from trading.strategy_adapter import evaluate_strategies; print('OK')"`
- **Pure function test:** `ticks_to_snapshot()` can be called standalone with synthetic MarketInfo + Tick objects
- **Log lines:** Look for `[ADAPTER]` prefix in both `log` (INFO) and `debug_log` (DEBUG) outputs
- **Failure shapes:** Balance fetch failure → warning log + empty list. Bad tick data → immediate TypeError/ValueError. Strategy exception → caught per-strategy, debug logged, loop continues.

## Deviations

- **Import resolution via symlinks:** The plan assumed `cd src && PYTHONPATH=. python3 -c "from trading.strategy_adapter import ..."` would work directly. In reality, the worktree doesn't contain existing trading modules (they're untracked in the main repo, not in git). Symlinked all existing `trading/*.py` and `shared/db.py` from the main repo to make the import chain resolve. The full import still requires mocking `py_clob_client` (third-party package not installed in system Python). This is a development context issue, not a code issue — the adapter is correct.
- **Verification used AST + mock imports** instead of bare import, since `py_clob_client` is not installed. The S03 verify script (T02) will handle this properly.

## Known Issues

- Full import requires `py_clob_client` package (trading runtime dependency not installed in dev environment). Verification uses mock-based imports. The T02 verification script should follow the same mock pattern.

## Files Created/Modified

- `src/trading/strategy_adapter.py` — NEW: adapter module with `ticks_to_snapshot()`, `_populate_execution_fields()`, and `evaluate_strategies()`
- `src/trading/__init__.py` — symlink to main repo's trading `__init__.py` (for import resolution)
- `src/trading/*.py` — symlinks to main repo's existing modules (balance, db, constants, strategies, utils, etc.)
- `src/shared/db.py` — symlink to main repo's `shared/db.py` (transitive dependency for `trading.db`)
- `.gsd/milestones/M001/slices/S03/S03-PLAN.md` — added failure-path diagnostic verification checks (pre-flight fix)
- `.gsd/milestones/M001/slices/S03/tasks/T01-PLAN.md` — added Observability Impact section (pre-flight fix)
