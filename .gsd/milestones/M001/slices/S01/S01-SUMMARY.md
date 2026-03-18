---
id: S01
parent: M001
milestone: M001
provides:
  - StrategyConfig, MarketSnapshot, Signal, BaseStrategy dataclasses in shared/strategies/base.py
  - Folder-based strategy registry (discover_strategies, get_strategy) in shared/strategies/registry.py
  - S1 spike reversion strategy with production M3_CONFIG parameters
  - verify_s01.py contract verification script (18 checks)
requires: []
affects:
  - S02
  - S03
key_files:
  - src/shared/strategies/base.py
  - src/shared/strategies/registry.py
  - src/shared/strategies/__init__.py
  - src/shared/strategies/S1/config.py
  - src/shared/strategies/S1/strategy.py
  - src/scripts/verify_s01.py
key_decisions:
  - Signal carries all 10 executor-required fields with zero/empty defaults for execution fields (D006)
  - MarketSnapshot.prices is numpy ndarray indexed by elapsed second with NaN for missing data (D002, D004)
  - Registry silently skips broken strategy modules — diagnosable by comparing folder listing vs registry output
  - Down-spike detection simplified to min_price <= spike_threshold_down (mathematically equivalent to original)
patterns_established:
  - Strategy folder convention — shared/strategies/{ID}/ contains __init__.py, config.py (with get_default_config()), strategy.py (BaseStrategy subclass)
  - NaN handling — ~np.isnan() mask → np.any(valid_mask) guard → valid_prices = window[valid_mask]
  - Signal data contract — strategy sets direction/strategy_name/entry_price/signal_data; trading adapter fills locked_* fields
  - Registry auto-discovery — importlib scans shared/strategies/*/strategy.py, lazy init on first get_strategy() call
observability_surfaces:
  - "discover_strategies() returns dict[str, type[BaseStrategy]] — inspectable for what loaded"
  - "get_strategy('UNKNOWN') raises KeyError listing available strategy IDs"
  - "dataclasses.fields(Signal) introspectable for schema validation"
  - "verify_s01.py exit code 0/1 as automated contract check"
drill_down_paths:
  - .gsd/milestones/M001/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S01/tasks/T02-SUMMARY.md
duration: 22m
verification_result: passed
completed_at: 2026-03-18
---

# S01: Shared strategy framework + data model

**Established shared/strategies/ package with base types (StrategyConfig, MarketSnapshot, Signal, BaseStrategy), folder-based auto-discovery registry, and S1 spike reversion as first concrete strategy — importable and unit-tested, ready for adapter wiring**

## What Happened

Built the shared strategy framework in two tasks. T01 created the foundation: four core types in `base.py` (StrategyConfig, MarketSnapshot, Signal, BaseStrategy ABC), a dynamic registry in `registry.py` that scans `shared/strategies/*/strategy.py` for BaseStrategy subclasses, and `__init__.py` re-exporting 6 public names. Signal includes all 10 fields the trading executor expects (direction, strategy_name, entry_price, signal_data, confidence_multiplier, created_at, locked_shares, locked_cost, locked_balance, locked_bet_size) with execution fields defaulting to zero/empty so strategies only set what they know.

T02 proved the framework works end-to-end by porting the M3 spike reversion strategy as S1. Ported `_find_spike()` and `_find_reversion()` from `analysis/backtest/module_3_mean_reversion.py`, operating on numpy arrays with NaN masking. Config parameters copied from `trading/constants.py` M3_CONFIG (spike_detection_window_seconds=15, spike_threshold_up=0.80, spike_threshold_down=0.20, reversion_reversal_pct=0.10, min_reversion_ticks=10, entry_price_threshold=0.35). Wrote an 18-check verification script covering imports, registry discovery, spike detection, flat-price rejection, NaN resilience, Signal field completeness, and import isolation.

The package has zero imports from `trading.*`, `analysis.*`, or `core.*` — only stdlib and numpy.

## Verification

All 4 slice-level verification checks pass:

| # | Check | Command | Result |
|---|-------|---------|--------|
| 1 | All public API importable | `from shared.strategies import BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy` | ✅ PASS |
| 2 | Registry discovers S1 | `get_strategy('S1').config.strategy_id == 'S1'` and `strategy_name == 'S1_spike_reversion'` | ✅ PASS |
| 3 | Full contract verification | `python3 scripts/verify_s01.py` — 18/18 checks pass | ✅ PASS |
| 4 | Error path diagnostic | `get_strategy('NONEXISTENT')` raises KeyError with `Available: ['S1']` | ✅ PASS |

Observability surfaces confirmed:
- `discover_strategies()` returns `{'S1': <class 'S1Strategy'>}` — correct inspectable mapping
- `get_strategy('NONEXISTENT')` error message includes available IDs
- `dataclasses.fields(Signal)` returns all 10 field names

## Requirements Advanced

- R001 — Framework exists: single strategy definition (config.py + strategy.py) in a shared location. Not yet consumed by both adapters (S02/S03).
- R002 — Folder convention proven: `shared/strategies/S1/` contains config + evaluate module, auto-discovered by registry.
- R003 — MarketSnapshot defined with numpy ndarray indexed by elapsed seconds. Not yet produced by adapters (S02/S03).
- R004 — Signal dataclass defined with all executor-required fields. Not yet consumed by analysis results (S02) or verified against executor (S03).
- R008 — Registry implemented: `discover_strategies()` scans folders, `get_strategy()` instantiates by ID.

## Requirements Validated

- R002 — `shared/strategies/S1/` exists with config.py and strategy.py; registry auto-discovers it; adding a strategy is adding a folder. Proven by verify_s01.py import isolation check + registry discovery.
- R008 — `discover_strategies()` returns `{'S1': S1Strategy}`, `get_strategy('S1')` instantiates correctly, `get_strategy('NONEXISTENT')` raises diagnostic KeyError. Fully proven by 4 verification checks.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- Used `python3` instead of `python` — system only has `python3` available. All plan commands adjusted at runtime.
- Verification script test data required calibration: plan's example reversion prices would have produced entry_price exceeding the 0.35 threshold. Adjusted reversion prices to 0.75 so entry_price = 0.25 ≤ 0.35.
- Down-spike detection simplified from `(1.0 - min_price) >= spike_threshold` to `min_price <= spike_threshold_down` — mathematically equivalent, clearer intent.

## Known Limitations

- Registry silently skips broken strategy modules (no logging). Diagnosable by comparing `os.listdir()` vs `discover_strategies().keys()`, but a future logging integration could surface this.
- `get_strategy()` always creates a new instance — no caching or singleton pattern. Fine for the current usage patterns.
- S1 strategy logic is ported as-is per D005; the specific parameters are disposable (R013).

## Follow-ups

- none — all expected work for this slice was completed.

## Files Created/Modified

- `src/shared/__init__.py` — package init for shared module
- `src/shared/strategies/__init__.py` — re-exports 6 public names (BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy)
- `src/shared/strategies/base.py` — four core types: StrategyConfig, MarketSnapshot (seconds-indexed numpy prices), Signal (10 executor fields), BaseStrategy ABC
- `src/shared/strategies/registry.py` — discover_strategies() folder scanner + get_strategy() instantiator with diagnostic KeyError
- `src/shared/strategies/S1/__init__.py` — empty package init
- `src/shared/strategies/S1/config.py` — S1Config dataclass with M3_CONFIG production parameters + get_default_config()
- `src/shared/strategies/S1/strategy.py` — S1Strategy implementing spike detection → reversion → contrarian signal on numpy arrays with NaN handling
- `src/scripts/verify_s01.py` — 18-check verification script (imports, registry, signals, NaN, defaults, isolation)

## Forward Intelligence

### What the next slice should know
- Import path is `from shared.strategies import get_strategy, MarketSnapshot, Signal` — these are the three things adapters need.
- `get_strategy('S1').evaluate(snapshot)` returns `Signal | None`. The strategy never raises on bad data; it returns None.
- `MarketSnapshot.prices` must be a numpy ndarray where index = elapsed second and NaN = missing tick. The adapter is responsible for building this from its data source.
- Signal's `locked_*` fields default to zero — the trading adapter must populate them before passing to the executor.
- `signal_data` dict from evaluate() contains strategy-specific metadata (spike_direction, peak prices, reversion details). The trading adapter can merge its own keys (bet_cost, shares, etc.) into this dict.

### What's fragile
- `discover_strategies()` uses `importlib.import_module()` with hardcoded path pattern `shared.strategies.{folder}.strategy` — if PYTHONPATH doesn't include `src/`, imports fail silently and registry returns empty dict. Adapters must ensure PYTHONPATH is set.
- `get_strategy()` calls `get_default_config()` from `config.py` — every strategy folder **must** have this function or instantiation crashes with AttributeError (not a clean error message).

### Authoritative diagnostics
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — 18-check contract verification, exit code 0/1. This is the single command to run if anything seems broken.
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies import discover_strategies; print(discover_strategies())"` — shows exactly which strategies loaded.

### What assumptions changed
- Original plan assumed `python` command available — only `python3` works on this system. All downstream slices should use `python3`.
- S1's entry_price_threshold (0.35) is stricter than some test scenarios assume. Test data for spike reversion must produce entry_price ≤ 0.35 or evaluate() returns None.
