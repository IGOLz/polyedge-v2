---
estimated_steps: 4
estimated_files: 20
---

# T01: Restore source tree from implementation commit

**Slice:** S01 — Apply unified report implementation and verify
**Milestone:** M002

## Description

The working tree (`milestone/M002` branch HEAD at `6a886ff`) has no `src/` files. All implementation code — both the M001 foundation (base.py, registry.py, S1/, S2/, TEMPLATE/) and the M002 deliverables (report.py, updated backtest_strategies.py, trading/report.py, verify_reports.py) — exists in commit `777a474`. This task restores the full source tree so that imports and verification can proceed.

## Steps

1. Checkout the entire `src/` directory from commit `777a474` using `git checkout 777a474 -- src/`
2. Convert any symlinks to real files — `777a474` tracked `trading/main.py` and other trading files as symlinks to the main repo; these need to either be resolved or confirmed present
3. Verify the M001 foundation imports work: `from shared.strategies import BaseStrategy, discover_strategies`
4. Verify the M002 report import works: `from shared.strategies.report import StrategyReport`

## Must-Haves

- [ ] `src/shared/strategies/report.py` exists on disk (310 lines, StrategyReport dataclass)
- [ ] `src/shared/strategies/base.py` exists on disk (M001 foundation)
- [ ] `src/shared/strategies/registry.py` exists on disk (M001 foundation)
- [ ] `src/shared/strategies/S1/`, `S2/`, `TEMPLATE/` directories exist with config.py + strategy.py
- [ ] `src/analysis/backtest_strategies.py` contains `_generate_reports()` function
- [ ] `src/trading/report.py` exists (379 lines, compute_live_metrics + generate_live_reports)
- [ ] `src/scripts/verify_reports.py` exists (264 lines, 47 checks)
- [ ] `from shared.strategies.report import StrategyReport` succeeds

## Verification

- `ls src/shared/strategies/report.py src/trading/report.py src/scripts/verify_reports.py` — all exist
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; print('OK')"` — prints OK
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies import StrategyReport; print(sorted(StrategyReport.__dataclass_fields__.keys()))"` — prints field names
- `grep -c '_generate_reports' src/analysis/backtest_strategies.py` — returns ≥1

## Observability Impact

- **What changes:** The `src/` directory tree goes from empty to fully populated. All Python modules become importable.
- **Inspection:** `find src -type f -name '*.py' | wc -l` gives file count. `ls -la src/trading/` reveals any broken symlinks. Standard Python import errors (ModuleNotFoundError) surface missing files.
- **Failure state:** If `git checkout` partially fails, `git status` shows which files were staged vs missing. Broken symlinks appear as red entries in `ls -la --color`.

## Inputs

- Commit `777a474` — contains all implementation code for both M001 and M002
- Current HEAD `6a886ff` — has only `.gsd/` metadata, no `src/` files

## Expected Output

- Full `src/` directory tree restored with all M001 foundation and M002 implementation files
- All Python imports for the report pipeline resolve successfully
