---
id: S03
parent: M001
milestone: M001
provides:
  - trading/strategy_adapter.py — ticks_to_snapshot() + evaluate_strategies() bridging shared strategies into the trading bot
  - trading/main.py import rewired to use shared adapter instead of hardcoded strategies
  - scripts/verify_s03.py — 18-check contract verification for the full trading adapter pipeline
requires:
  - slice: S01
    provides: shared/strategies/ base classes (MarketSnapshot, Signal, BaseStrategy), registry (discover_strategies, get_strategy), S1 strategy
affects:
  - S04
key_files:
  - src/trading/strategy_adapter.py
  - src/trading/main.py
  - src/scripts/verify_s03.py
key_decisions:
  - Followed D008 composition pattern — adapter composes shared.strategies + existing trading infrastructure without modifying either side
  - Live context elapsed_seconds uses wall-clock time (differs from S02 backtest where elapsed == total)
  - Profitability thesis built dynamically from signal_data context keys rather than hardcoded per-strategy
patterns_established:
  - Trading adapter mirrors S02 analysis adapter composition pattern (D008) — new module composes shared.strategies + existing infrastructure, no modifications to either side
  - Worktree symlink pattern for untracked main-repo modules (trading/*.py, shared/db.py) enables development without shadowing packages
  - Mock-based verification for py_clob_client and other runtime-only trading dependencies
observability_surfaces:
  - "[ADAPTER] N signal(s) for MARKET_ID" — INFO log on signal generation
  - "[ADAPTER] skipping/already traded/no signals" — debug_log lines for each guard path
  - Strategy evaluation exceptions caught per-strategy with debug_log, loop continues
  - "cd src && PYTHONPATH=. python3 scripts/verify_s03.py" — exit code 0/1, 18 checks
drill_down_paths:
  - .gsd/milestones/M001/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S03/tasks/T02-SUMMARY.md
duration: 23m
verification_result: passed
completed_at: 2026-03-18
---

# S03: Trading adapter — live signals through shared strategies

**Built `trading/strategy_adapter.py` that converts live ticks to MarketSnapshot, evaluates shared strategies via registry, and produces executor-compatible Signal objects — rewired `trading/main.py` to use it with zero modifications to executor, redeemer, or balance**

## What Happened

Two tasks delivered the trading side of the shared strategy framework:

**T01 (15m)** built `trading/strategy_adapter.py` with three functions: `ticks_to_snapshot()` converts `MarketInfo` + `list[Tick]` into a `MarketSnapshot` with a numpy array indexed by elapsed second (NaN for missing seconds, last-write-wins for same-second ticks), using wall-clock `elapsed_seconds` for live context. `_populate_execution_fields()` fills all 4 `locked_*` fields and 12 executor-required `signal_data` keys using existing `calculate_dynamic_bet_size()` and `calculate_shares()` from `trading.strategies`. `evaluate_strategies()` is the async drop-in replacement — it guards on empty ticks, balance failure, already-traded, and bet-too-large, then iterates shared strategies via `discover_strategies()` + `get_strategy()`, calls `strategy.evaluate()` synchronously (D001), and returns `list[Signal]`.

**T02 (8m)** rewired the single import line in `trading/main.py` (line 20: `from trading.strategies import evaluate_strategies` → `from trading.strategy_adapter import evaluate_strategies`) and built `scripts/verify_s03.py` — an 18-check contract verification script covering import chains, tick-to-snapshot conversion (NaN gaps, correct indices), S1 strategy evaluation on calibrated spike-reversion data, all executor-required field population, empty-ticks guard, R009 file hash integrity, and module isolation.

The key architectural insight: the trading adapter follows the exact same composition pattern as S02's analysis adapter (D008) — a new entry-point module composes `shared.strategies` with existing trading infrastructure (`trading.balance`, `trading.db`, `trading.constants`) without modifying either side. Both adapters are now symmetric: `analysis/backtest_strategies.py` for historical data and `trading/strategy_adapter.py` for live ticks, both producing MarketSnapshot and running shared strategies.

## Verification

`cd src && PYTHONPATH=. python3 scripts/verify_s03.py` — 18/18 checks pass:

- **Import chain** (checks 1-3): adapter, shared strategies, and async signature all resolve
- **Tick-to-snapshot** (checks 4-7): correct MarketSnapshot shape, NaN for gap seconds, correct values at known indices, elapsed_seconds reflects live context
- **Strategy evaluation** (checks 8-10): S1 fires on calibrated spike data, direction is 'Down' (contrarian), signal_data contains strategy-specific keys
- **Executor fields** (checks 11-14): locked_shares > 0, locked_cost > 0, price_min/price_max present, profitability_thesis is non-empty
- **Guards** (check 15): empty ticks → all-NaN array, no crash
- **R009 integrity** (checks 16-17): executor.py, redeemer.py, balance.py SHA-256 hashes match originals
- **Module isolation** (check 18): no `analysis.*` or `core.*` imports in adapter

Additional verification: `grep` confirms main.py import rewired; old import absent.

## Requirements Advanced

- R001 — S1 is now consumed by both analysis (S02) and trading (S03) adapters via the shared registry. Single definition, dual consumption proven. Formal parity proof remains for S04.
- R003 — Trading adapter produces MarketSnapshot with prices indexed by elapsed seconds, matching the analysis adapter's convention. Both sides now use the same time axis. Formal parity proof remains for S04.
- R004 — Shared Signal type flows from strategy.evaluate() through the trading adapter and carries all executor-required fields. Same Signal type used by both adapters.
- R008 — Trading adapter uses `discover_strategies()` + `get_strategy()` from the shared registry. No hardcoded strategy imports.

## Requirements Validated

- R006 — verify_s03.py proves the full pipeline: live ticks → MarketSnapshot → shared strategy evaluate() → Signal with all executor-required fields populated. 18/18 checks pass.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- **Worktree symlinks for import resolution**: The plan assumed `PYTHONPATH=.` would resolve all imports directly. In practice, existing `trading/*.py` modules aren't in git (untracked in main repo), so the worktree doesn't have them. Symlinked all existing modules from the main repo into the worktree. This is a development-context issue (documented in KNOWLEDGE.md), not a code change — the adapter itself is correct.
- **Mock-based verification**: `py_clob_client` (third-party trading SDK) is not installed in the dev Python environment. All verification scripts mock it before importing trading modules. This is consistent with S01/S02 patterns.

## Known Limitations

- **Full import requires runtime mocking of `py_clob_client`**: The trading SDK is a runtime dependency not installed in the development environment. Verification scripts handle this with `sys.modules` mocking, but any new test tooling must follow the same pattern.
- **`elapsed_seconds` uses wall-clock time**: In live context, `elapsed_seconds` is computed from `datetime.now(UTC) - market.started_at`. This is correct for live trading but means the S04 parity test must account for the difference (S02 backtest uses `elapsed == total`).
- **Parity not yet formally proven**: Both adapters produce MarketSnapshot and run shared strategies, but identical-input → identical-output has not been verified in a single test. Deferred to S04.

## Follow-ups

- S04 parity test must feed identical price data through both adapters and assert identical Signal output — this is the final proof that the framework eliminates the seconds-vs-ticks bug.
- S04 should test with `elapsed_seconds == total_seconds` in both adapters (full data scenario) to isolate the comparison from the live-vs-backtest elapsed difference.

## Files Created/Modified

- `src/trading/strategy_adapter.py` — NEW: adapter module with `ticks_to_snapshot()`, `_populate_execution_fields()`, and `evaluate_strategies()`
- `src/trading/main.py` — MODIFIED: 1-line import change (line 20: `trading.strategies` → `trading.strategy_adapter`)
- `src/scripts/verify_s03.py` — NEW: 18-check contract verification script for S03 pipeline

## Forward Intelligence

### What the next slice should know
- Both adapters are now symmetric: `analysis/backtest_strategies.py` (historical) and `trading/strategy_adapter.py` (live). Both produce MarketSnapshot → strategy.evaluate() → Signal. The parity test (S04) should construct identical price arrays and feed them through both, asserting Signal equality.
- The trading adapter's `ticks_to_snapshot()` is a pure function — easy to call in a parity test with synthetic Tick objects. The analysis adapter's conversion is in `backtest_strategies.py` `_market_to_snapshot()`.
- S1 synthetic data calibration is documented in KNOWLEDGE.md: spike peak at s=4-5, sharp reversion (0.85→0.75 in 3-4 steps), entry_price ≤ 0.35.

### What's fragile
- **`elapsed_seconds` semantics differ between adapters**: Trading uses wall-clock elapsed (< total), backtest uses total. Parity test must either (a) override elapsed in both to match, or (b) set wall-clock to exactly match the total duration of the synthetic data. If S1 uses `elapsed_seconds` in its evaluate logic, this difference could cause signal divergence even on identical price data.
- **Symlink-based import resolution**: The worktree relies on symlinks to main-repo trading modules. If main-repo files are renamed or restructured, symlinks break silently. The verify_s03.py hash checks would catch modifications but not renames.

### Authoritative diagnostics
- `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` — exit code 0/1, 18 checks covering full pipeline. This is the single source of truth for S03 correctness.
- `grep "from trading.strategy_adapter import evaluate_strategies" src/trading/main.py` — confirms the rewire is in place.
- verify_s03.py checks 16-17 (R009 hash integrity) will fail visibly if executor.py, redeemer.py, or balance.py are ever modified.

### What assumptions changed
- **Assumed direct imports would work in worktree** — actual: worktree requires symlinks for untracked modules and mock-based imports for `py_clob_client`. This is now a documented pattern in KNOWLEDGE.md.
- **Assumed verification would test actual async execution** — actual: verification uses synchronous mock-based tests since the full async runtime (event loop + DB pool + trading SDK) isn't available in dev. Async signature is verified via `inspect.iscoroutinefunction()`.
