---
id: S02
parent: M001
milestone: M001
provides:
  - analysis/backtest_strategies.py — adapter module bridging shared strategies into the existing backtest engine
  - market_to_snapshot() — converts data_loader market dicts to MarketSnapshot (seconds-indexed)
  - run_strategy() — evaluates a shared strategy against markets and produces (trades, metrics)
  - CLI entry point: python3 -m analysis.backtest_strategies --strategy S1
  - Contract verification script: scripts/verify_s02.py (18 checks, no DB)
requires:
  - slice: S01
    provides: shared/strategies/{base.py, registry.py, S1/} — BaseStrategy, MarketSnapshot, Signal, get_strategy, discover_strategies
affects:
  - S04 (parity verification consumes the backtest adapter pattern)
  - S05 (optimization script builds on backtest_strategies runner)
key_files:
  - src/analysis/backtest_strategies.py
  - src/scripts/verify_s02.py
key_decisions:
  - Adapter pattern: new module composes shared.strategies + analysis.backtest.engine without modifying either
  - Signal→Trade bridge extracts entry_second from signal_data via .get('reversion_second', 0) with fallback to 0
  - elapsed_seconds = total_seconds in backtest mode (full market data available for evaluation)
  - Read-only dependencies (engine, data_loader, config) copied into worktree for import chain — untracked in main repo
patterns_established:
  - Adapter composition pattern: new entry point wires shared framework to existing infrastructure, zero modifications to either side
  - market_to_snapshot() as the canonical conversion from data_loader dict → MarketSnapshot for backtest context
  - Contract verification via numbered check scripts (verify_s02.py follows verify_s01.py pattern)
observability_surfaces:
  - stdout progress per strategy: "[{id}] Evaluating N markets → M trades"
  - CLI --help as module integrity check
  - Saved CSV/markdown/best-configs artifacts in --output-dir
  - Zero-trade strategies produce total_bets=0 in metrics (visible, not hidden)
  - verify_s02.py exit code 0/1 as CI-ready health check
drill_down_paths:
  - .gsd/milestones/M001/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S02/tasks/T02-SUMMARY.md
duration: 24m
verification_result: passed
completed_at: 2026-03-18
---

# S02: Analysis adapter — backtest through shared strategies

**Created analysis/backtest_strategies.py that loads shared strategies from the registry, converts historical market data to MarketSnapshot, evaluates strategies, and produces backtest metrics through the existing engine — zero modifications to any existing file.**

## What Happened

S02 delivered one new module (`analysis/backtest_strategies.py`, ~160 lines) and one verification script (`scripts/verify_s02.py`, 18 checks). Together they prove that the shared strategy framework from S01 integrates cleanly with the existing analysis backtest infrastructure.

**T01** built the adapter module with three components:
1. `market_to_snapshot(market_dict) → MarketSnapshot` — maps data_loader's market dict format to the shared MarketSnapshot type. Sets `elapsed_seconds = total_seconds` (backtest convention: full price series available). Populates metadata with asset, hour, started_at, final_outcome, duration_minutes.
2. `run_strategy(strategy_id, strategy, markets) → (trades, metrics)` — loops markets, converts to snapshots, calls `strategy.evaluate()`, bridges Signal → Trade via `engine.make_trade()` (using `signal_data['reversion_second']` as entry second), and computes metrics via `engine.compute_metrics()`.
3. `main()` with argparse CLI — supports `--strategy` (single or all), `--output-dir`, `--assets`, `--durations`. Loads data, discovers strategies from registry, runs each, builds DataFrame with `add_ranking_score()`, saves with `save_module_results()`.

**T02** built the contract verification script following the verify_s01.py pattern. It constructs synthetic market data with a calibrated spike+reversion price curve that triggers S1's detection thresholds, then validates every stage of the pipeline: import → conversion → evaluation → trade creation → metrics computation → integration → module isolation. The synthetic data required careful calibration — S1's `min_reversion_ticks=10` window and `reversion_reversal_pct=0.10` threshold demand a sharp spike peak early in the detection window (by s=4-5) with a steep drop (0.85→0.75) rather than a gradual decline.

No existing files in `analysis/`, `trading/`, or `core/` were modified.

## Verification

All three slice-level verification checks pass:

| Check | Command | Result |
|-------|---------|--------|
| Contract verification (18 checks) | `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` | ✅ 18/18 pass, exit 0 |
| CLI integrity | `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --help` | ✅ Shows usage with all flags |
| Empty-market diagnostic | `run_strategy('S1', s, [])` with zero markets | ✅ Returns total_bets=0 without error |

Observability surfaces confirmed:
- Progress output prints `[S1] Evaluating N markets → M trades` per strategy
- CLI `--help` displays all four flags (--strategy, --output-dir, --assets, --durations)
- Module isolation verified via AST inspection: no `trading.*` or `core.*` imports

Integration verification (`--strategy S1` with real DB) deferred — requires database connection not available in worktree. This is expected; full integration is validated when the module runs against the production database.

## Requirements Advanced

- R001 — Analysis adapter now consumes the shared strategy definition (S1) without duplication. The analysis side of "consumed by both analysis and trading" is proven. Trading side remains for S03.
- R003 — Analysis adapter produces MarketSnapshot with `elapsed_seconds = total_seconds` (seconds-indexed). The analysis half of "both analysis and trading produce seconds-indexed snapshots" is established. Trading half remains for S03.
- R005 — Directly fulfilled: analysis converts historical data to MarketSnapshot, runs shared evaluate(), and collects backtest results. Contract-verified on synthetic data; full DB integration deferred to runtime.
- R012 — Supporting infrastructure delivered: `run_strategy()` is the building block the optimization script (S05) will call in a grid-search loop.

## Requirements Validated

- R005 — `verify_s02.py` proves the full pipeline on synthetic data: market dict → MarketSnapshot → strategy.evaluate() → Signal → Trade → metrics. 18/18 checks pass. Full DB integration deferred to runtime but the contract is proven.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- **Synthetic price data redesign (T02):** The plan's loop-based gradual ramp produced insufficient reversion within S1's `min_reversion_ticks=10` window (~0.08, below the 0.10 threshold). Switched to explicit array values with a faster spike (5 seconds to peak) and sharper drop (0.85→0.75 in 4 steps), giving reversion≈0.118 with margin. Same calibration knowledge documented in KNOWLEDGE.md from S01.
- **Read-only dependency copies (T01):** Copied `analysis/backtest/{engine.py, data_loader.py, __init__.py}`, `analysis/__init__.py`, and `shared/config.py` into the worktree. These files exist in the main repo but weren't present in the milestone branch. Required for data_loader's import chain to resolve. Files are untracked in the main repo.

## Known Limitations

- **DB integration untested in worktree:** `python3 -m analysis.backtest_strategies --strategy S1` requires a live database connection. The contract verification proves the pipeline on synthetic data, but full integration with real market data is only validated at runtime against the production DB.
- **Single strategy tested:** Only S1 is available. Multi-strategy discovery path (`--strategy` omitted, runs all) exercises the same code path but with a single strategy. S04 adds S2 for multi-strategy coverage.

## Follow-ups

- none (all discovered work fits within planned S03–S05 slices)

## Files Created/Modified

- `src/analysis/backtest_strategies.py` — NEW: adapter module with market_to_snapshot(), run_strategy(), main(), __main__ guard (~160 lines)
- `src/scripts/verify_s02.py` — NEW: 18-check contract verification script, synthetic data, full pipeline validation
- `src/analysis/__init__.py` — COPIED from main repo (read-only dependency)
- `src/analysis/backtest/__init__.py` — COPIED from main repo (read-only dependency)
- `src/analysis/backtest/engine.py` — COPIED from main repo (read-only dependency)
- `src/analysis/backtest/data_loader.py` — COPIED from main repo (read-only dependency)
- `src/shared/config.py` — COPIED from main repo (read-only dependency for data_loader import chain)

## Forward Intelligence

### What the next slice should know
- The adapter pattern is simple: new module imports from both `shared.strategies` and `analysis.backtest.engine`, composes them, modifies neither. S03 (trading adapter) should follow the same structure — import shared strategies + trading infra, compose without modifying.
- `market_to_snapshot()` is the canonical conversion for backtest context. S03 needs its own `ticks_to_snapshot()` for live tick streams, but the MarketSnapshot output shape is identical.
- `run_strategy()` returns `(trades, metrics)` — S05's optimization script can call this directly in a loop over config variations.

### What's fragile
- **S1 synthetic data thresholds** — the spike+reversion test data is carefully tuned to S1's exact thresholds (spike_threshold_up=0.80, reversion_reversal_pct=0.10, entry_price_threshold=0.35, min_reversion_ticks=10). If S1's config changes, both verify_s01.py and verify_s02.py synthetic data will need recalibration.
- **Signal→Trade bridge assumes reversion_second** — `signal_data.get('reversion_second', 0)` works for S1 but other strategies may use different entry point semantics. The fallback to 0 is safe but may not be meaningful for all strategy types.

### Authoritative diagnostics
- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — single command proving the full adapter pipeline works. Exit 0 = healthy. First `[FAIL]` line pinpoints the broken stage.
- `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --help` — proves the module's import chain resolves cleanly.

### What assumptions changed
- **No assumptions changed.** The S01 boundary map accurately described what was needed. The adapter consumed shared types exactly as specified and the existing engine functions accepted the adapter's output without modification.
