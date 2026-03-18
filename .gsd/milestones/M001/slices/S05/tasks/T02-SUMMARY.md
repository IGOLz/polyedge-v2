---
id: T02
parent: S05
milestone: M001
provides:
  - Grid-search parameter optimizer CLI (analysis/optimize.py) with dry-run and ranking (R012)
  - get_param_grid() search space definitions for S1 and S2 strategies
key_files:
  - src/analysis/optimize.py
  - src/shared/strategies/S1/config.py
  - src/shared/strategies/S2/config.py
key_decisions: []
patterns_established:
  - get_param_grid() convention on strategy config modules — returns dict[str, list] of param names to candidate values
  - dataclasses.replace() for config overrides — preserves strategy_id/strategy_name from get_default_config()
  - Lazy data loading — dry-run skips DB access entirely by deferring data_loader import
observability_surfaces:
  - "Dry-run prints grid summary: param names, values, total combinations — verifiable without DB"
  - "Full run prints per-combination progress and top-10 ranking summary to stdout"
  - "Results artifacts in results/optimization/: CSV, best configs, analysis markdown"
  - "Missing get_param_grid() → printed skip message, no traceback"
  - "TEMPLATE/nonexistent strategy → clear error message with available IDs"
duration: 12m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T02: Build parameter optimization script with grid-search CLI

**Added grid-search optimizer (analysis/optimize.py) with --dry-run/--strategy CLI, plus get_param_grid() for S1 and S2 defining 27-combination search spaces each**

## What Happened

Added `get_param_grid()` functions to S1 and S2 config modules, each returning 3 parameters × 3 values = 27 combinations. Created `analysis/optimize.py` which discovers strategies via the registry, dynamically imports param grids, generates Cartesian products, backtests each combination via `run_strategy()`, ranks results with `add_ranking_score()`, and saves output via `save_module_results()`. The `--dry-run` flag prints the grid summary and exits without touching the database (data_loader import is deferred). TEMPLATE and strategies without `get_param_grid()` are explicitly skipped with clear messages.

## Verification

- S1 and S2 `get_param_grid()` both return non-empty dicts with correct param names and value lists
- `--dry-run` for S1 prints 27 combinations and exits 0
- `--dry-run` for S2 prints 27 combinations and exits 0
- TEMPLATE strategy is blocked with descriptive error
- Nonexistent strategy lists available IDs
- All three regression scripts pass: parity_test (24/24), verify_s01 (all), verify_s02 (18/18)
- All three strategies discoverable in registry

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python3 -c "from shared.strategies.S1.config import get_param_grid; ..."` | 0 | ✅ pass | <1s |
| 2 | `python3 -c "from shared.strategies.S2.config import get_param_grid; ..."` | 0 | ✅ pass | <1s |
| 3 | `python3 -m analysis.optimize --strategy S1 --dry-run` | 0 | ✅ pass | <1s |
| 4 | `python3 -m analysis.optimize --strategy S2 --dry-run` | 0 | ✅ pass | <1s |
| 5 | `python3 scripts/parity_test.py` | 0 | ✅ pass | 10s |
| 6 | `python3 scripts/verify_s01.py` | 0 | ✅ pass | 10s |
| 7 | `python3 scripts/verify_s02.py` | 0 | ✅ pass | 10s |
| 8 | `python3 -m analysis.optimize --strategy TEMPLATE --dry-run` | 1 | ✅ pass (expected error) | <1s |
| 9 | `python3 -c "...discover_strategies()...assert not missing..."` | 0 | ✅ pass | <1s |

## Diagnostics

- **Dry-run inspection:** `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` — prints param names, values, and 27 combinations without DB access.
- **Param grid check:** `python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid())"` — inspect search space for any strategy.
- **Full run output:** After `python3 -m analysis.optimize --strategy S1`, results land in `results/optimization/` with CSV rankings, best-configs text, and analysis markdown.
- **Failure signals:** Missing `get_param_grid()` → `"Strategy X has no get_param_grid() — skipping"` printed to stdout. TEMPLATE → `"Cannot optimize TEMPLATE"` + exit 1. Unknown strategy → `"Strategy X not found. Available: [...]"` + exit 1.

## Deviations

None — implementation follows the task plan exactly.

## Known Issues

None.

## Files Created/Modified

- `src/analysis/optimize.py` — new: grid-search optimizer with CLI (--strategy, --dry-run, --output-dir, --assets, --durations)
- `src/shared/strategies/S1/config.py` — modified: added `get_param_grid()` returning 3×3×3 search space
- `src/shared/strategies/S2/config.py` — modified: added `get_param_grid()` returning 3×3×3 search space
- `.gsd/milestones/M001/slices/S05/S05-PLAN.md` — modified: added Observability / Diagnostics section
- `.gsd/milestones/M001/slices/S05/tasks/T02-PLAN.md` — modified: added Observability Impact section
