---
id: S05
parent: M001
milestone: M001
provides:
  - TEMPLATE strategy skeleton for creating new strategies (R011)
  - Grid-search parameter optimization CLI with dry-run and ranking (R012)
  - get_param_grid() convention for strategy config modules
requires:
  - slice: S04
    provides: S2 strategy ported, parity test proven, framework correctness confirmed
  - slice: S02
    provides: backtest_strategies.run_strategy() and engine ranking functions consumed by optimizer
affects: []
key_files:
  - src/shared/strategies/TEMPLATE/__init__.py
  - src/shared/strategies/TEMPLATE/config.py
  - src/shared/strategies/TEMPLATE/strategy.py
  - src/shared/strategies/TEMPLATE/README.md
  - src/analysis/optimize.py
  - src/shared/strategies/S1/config.py
  - src/shared/strategies/S2/config.py
key_decisions:
  - D011 — TEMPLATE evaluate() returns None instead of raising NotImplementedError (parity_test safety)
patterns_established:
  - TEMPLATE folder as copy-and-customize starting point for new strategies
  - get_param_grid() convention on strategy config modules — returns dict[str, list] of param names to candidate values
  - dataclasses.replace() for config overrides in optimizer — preserves strategy_id/strategy_name from get_default_config()
  - Lazy data loading in optimizer — dry-run skips DB access entirely
observability_surfaces:
  - "discover_strategies() includes TEMPLATE — absence means import failure"
  - "parity_test.py check 6 auto-tests TEMPLATE — regression-visible if evaluate() breaks"
  - "Dry-run prints grid summary: param names, values, total combinations — verifiable without DB"
  - "Full optimizer run prints per-combination progress and top-10 ranking to stdout"
  - "Results artifacts in results/optimization/: CSV rankings, best configs, analysis markdown"
  - "Missing get_param_grid() → printed skip message, no traceback"
drill_down_paths:
  - .gsd/milestones/M001/slices/S05/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S05/tasks/T02-SUMMARY.md
duration: 20m
verification_result: passed
completed_at: 2026-03-18
---

# S05: Strategy template + parameter optimization

**Documented TEMPLATE strategy skeleton for creating new strategies, plus grid-search parameter optimizer CLI (`analysis.optimize`) with dry-run mode and ranking — completing the milestone's full strategy lifecycle from creation to tuning**

## What Happened

Two tasks delivered the final slice of M001:

**T01 — TEMPLATE strategy skeleton.** Created `shared/strategies/TEMPLATE/` with four files matching the proven S1/S2 directory pattern: `__init__.py` (package marker), `config.py` (TemplateConfig dataclass with example fields and `get_default_config()`), `strategy.py` (TemplateStrategy with `evaluate()` returning `None` and inline TODO guides), and `README.md` (step-by-step instructions for creating a new strategy). The TEMPLATE is auto-discovered by the registry alongside S1 and S2. Its `evaluate()` returns `None` rather than raising NotImplementedError (D011), which keeps parity_test.py check 6 green — that check auto-evaluates all discovered strategies.

**T02 — Grid-search parameter optimizer.** Added `get_param_grid()` functions to S1 and S2 config modules, each returning 3 parameters × 3 values = 27 combinations. Created `analysis/optimize.py` as a CLI module (`python -m analysis.optimize --strategy S1 --dry-run`) that discovers strategies via the registry, dynamically imports param grids, generates Cartesian products via `itertools.product`, backtests each combination via `run_strategy()`, ranks results with `add_ranking_score()`, and saves output via `save_module_results()`. The `--dry-run` flag prints the grid summary and exits without DB access (data_loader import is deferred). TEMPLATE and strategies without `get_param_grid()` are explicitly skipped with clear messages.

## Verification

All 11 slice-level verification checks pass:

| # | Check | Result |
|---|-------|--------|
| 1 | TEMPLATE import (TemplateStrategy + get_default_config) | ✅ pass |
| 2 | Registry discovers TEMPLATE alongside S1, S2 | ✅ pass — `['S1', 'S2', 'TEMPLATE']` |
| 3 | evaluate() returns None on flat prices (safe no-op) | ✅ pass |
| 4 | S1 get_param_grid() returns non-empty dict | ✅ pass — 3×3×3 = 27 combos |
| 5 | S2 get_param_grid() returns non-empty dict | ✅ pass — 3×3×3 = 27 combos |
| 6 | `python -m analysis.optimize --strategy S1 --dry-run` | ✅ pass — 27 combinations, exit 0 |
| 7 | `python -m analysis.optimize --strategy S2 --dry-run` | ✅ pass — 27 combinations, exit 0 |
| 8 | parity_test.py | ✅ pass — 24/24 checks |
| 9 | verify_s01.py | ✅ pass — 17/17 checks |
| 10 | verify_s02.py | ✅ pass — 18/18 checks |
| 11 | All strategies discoverable (diagnostic) | ✅ pass |

## Requirements Advanced

- R011 — TEMPLATE folder created with 4 files, registry discovers it, evaluate() returns None, parity_test.py passes
- R012 — Grid-search optimizer CLI created with dry-run mode, param grids defined for S1 and S2

## Requirements Validated

- R011 — TEMPLATE folder has all 4 files, is auto-discovered by registry, evaluate() safely returns None, parity_test.py check 6 auto-verifies it, README documents complete creation workflow
- R012 — `python -m analysis.optimize --strategy S1 --dry-run` prints grid (3 params × 3 values = 27 combos) and exits cleanly; optimizer skips TEMPLATE and strategies without get_param_grid(); results saved via save_module_results() with CSV rankings

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

None — both tasks followed their plans exactly.

## Known Limitations

- Full optimizer run (without --dry-run) requires a populated database with historical market data. Dry-run mode was verified; full backtest-and-rank mode was not exercised in CI-like conditions.
- TEMPLATE's README guides developers through the creation process but doesn't include automated validation that a new strategy's evaluate() actually produces signals (that's left to the developer's own testing).

## Follow-ups

- none — S05 is the final slice of M001. All milestone success criteria are met.

## Files Created/Modified

- `src/shared/strategies/TEMPLATE/__init__.py` — empty init for package discovery
- `src/shared/strategies/TEMPLATE/config.py` — TemplateConfig dataclass with example fields + get_default_config()
- `src/shared/strategies/TEMPLATE/strategy.py` — TemplateStrategy with evaluate() returning None + inline TODO comments
- `src/shared/strategies/TEMPLATE/README.md` — developer guide for creating new strategies
- `src/analysis/optimize.py` — grid-search optimizer with CLI (--strategy, --dry-run, --output-dir, --assets, --durations)
- `src/shared/strategies/S1/config.py` — added get_param_grid() returning 3×3×3 search space
- `src/shared/strategies/S2/config.py` — added get_param_grid() returning 3×3×3 search space

## Forward Intelligence

### What the next slice should know
- M001 is complete. The full strategy lifecycle is: create from TEMPLATE → implement evaluate() → add get_param_grid() → optimize with `python -m analysis.optimize`. Both analysis and trading consume strategies identically via the shared registry.
- The `get_param_grid()` convention is optional — strategies without it are silently skipped by the optimizer. This means new strategies can be added and used immediately without defining a search space.

### What's fragile
- The optimizer's full run path (non-dry-run) depends on `analysis.backtest_strategies.run_strategy()` and `analysis.backtest.engine` internals (add_ranking_score, save_module_results). If the engine's ranking or output API changes, the optimizer breaks.
- Registry auto-discovery silently ignores strategies with import errors — a broken strategy folder simply disappears from `discover_strategies()`. The diagnostic command `python3 -c "from shared.strategies.TEMPLATE.strategy import TemplateStrategy"` surfaces the actual traceback.

### Authoritative diagnostics
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; print(sorted(discover_strategies().keys()))"` — must show `['S1', 'S2', 'TEMPLATE']`. If any strategy is missing, it has an import error.
- `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` — confirms optimizer CLI works without DB access.
- `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — 24/24 checks confirm framework correctness including TEMPLATE.

### What assumptions changed
- No assumptions changed — S05 was low-risk and delivered exactly as planned.
