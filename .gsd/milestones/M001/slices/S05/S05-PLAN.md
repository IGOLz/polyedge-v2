# S05: Strategy template + parameter optimization

**Goal:** A documented strategy template for creating new strategies, and a grid-search parameter optimization script for tuning strategy configs against backtest data.
**Demo:** `shared/strategies/TEMPLATE/` contains a complete skeleton that the registry discovers. `python -m analysis.optimize --strategy S1` grid-searches S1's parameter space and ranks results.

## Must-Haves

- `shared/strategies/TEMPLATE/` with `__init__.py`, `config.py`, `strategy.py`, and `README.md` following the proven S1/S2 pattern
- TEMPLATE is auto-discovered by `discover_strategies()` and returns `None` from `evaluate()` (safe no-op, not NotImplementedError)
- `README.md` inside TEMPLATE with step-by-step instructions for creating a new strategy
- `get_param_grid()` function added to S1 and S2 config modules returning search ranges
- `analysis/optimize.py` module runnable as `python -m analysis.optimize --strategy S1` with grid-search and ranking
- `--dry-run` flag on optimizer that prints the grid and combination count without running backtests
- Optimizer skips TEMPLATE and strategies without `get_param_grid()`
- All existing verification scripts pass (verify_s01.py, verify_s02.py, parity_test.py)

## Verification

- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.TEMPLATE.strategy import TemplateStrategy; from shared.strategies.TEMPLATE.config import get_default_config; s = TemplateStrategy(get_default_config()); print('OK')"` — imports cleanly
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; d = discover_strategies(); assert 'TEMPLATE' in d; print('Discovered:', sorted(d.keys()))"` — registry discovers TEMPLATE alongside S1, S2
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.TEMPLATE.config import get_default_config; from shared.strategies.TEMPLATE.strategy import TemplateStrategy; s = TemplateStrategy(get_default_config()); from shared.strategies.base import MarketSnapshot; import numpy as np; r = s.evaluate(MarketSnapshot(market_id='test', market_type='test', prices=np.array([0.5]*60), total_seconds=60, elapsed_seconds=60)); assert r is None; print('evaluate() returns None: OK')"` — safe no-op confirmed
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S1.config import get_param_grid; g = get_param_grid(); assert len(g) > 0; print('S1 grid:', g)"` — S1 has param grid
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S2.config import get_param_grid; g = get_param_grid(); assert len(g) > 0; print('S2 grid:', g)"` — S2 has param grid
- `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` — prints grid, combination count, exits 0
- `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — all checks pass (regression + TEMPLATE auto-tested by check 6)
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — all checks pass
- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — all checks pass
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; d = discover_strategies(); missing = [s for s in ['S1','S2','TEMPLATE'] if s not in d]; assert not missing, f'Missing: {missing}'; print('All strategies discoverable')"` — diagnostic: confirms no strategy silently dropped from registry

## Observability / Diagnostics

- **Grid-search progress:** `optimize.py` prints `[{config_label}] Evaluating N markets → M trades` per combination via `run_strategy()` — live progress in stdout.
- **Dry-run inspection:** `python -m analysis.optimize --strategy S1 --dry-run` prints param names, value lists, and total combination count without touching the DB.
- **Results artifacts:** After a full run, `results/optimization/` contains CSV rankings, best-config text, and analysis markdown — all produced by `save_module_results()`.
- **Strategy registry health:** `python3 -c "from shared.strategies.registry import discover_strategies; print(sorted(discover_strategies().keys()))"` — must show `['S1', 'S2', 'TEMPLATE']`. Missing strategy = silent import error in that folder.
- **Param grid validation:** `python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid())"` — quick check that a strategy's grid is defined and non-empty.
- **Failure visibility:** If a strategy's config module lacks `get_param_grid`, optimizer prints `"Strategy {id} has no get_param_grid() — skipping"` and returns cleanly (no exception).
- **Redaction:** No secrets or credentials involved — all data is local backtest results.

## Integration Closure

- Upstream surfaces consumed: `shared/strategies/base.py` (StrategyConfig, BaseStrategy, MarketSnapshot, Signal), `shared/strategies/registry.py` (discover_strategies), `analysis/backtest_strategies.py` (run_strategy), `analysis/backtest/engine.py` (add_ranking_score, save_module_results)
- New wiring introduced in this slice: `analysis/optimize.py` composes registry + backtest runner + engine ranking into a CLI; `get_param_grid()` convention added to strategy config modules
- What remains before the milestone is truly usable end-to-end: nothing — S05 is the final slice

## Tasks

- [x] **T01: Create TEMPLATE strategy folder with documented skeleton** `est:20m`
  - Why: Delivers R011 — a copy-and-customize starting point for new strategies. Must follow the proven S1/S2 directory pattern exactly so the registry auto-discovers it.
  - Files: `src/shared/strategies/TEMPLATE/__init__.py`, `src/shared/strategies/TEMPLATE/config.py`, `src/shared/strategies/TEMPLATE/strategy.py`, `src/shared/strategies/TEMPLATE/README.md`
  - Do: Create 4 files matching S1/S2 structure. `TemplateConfig(StrategyConfig)` with example fields and defaults. `TemplateStrategy(BaseStrategy)` with `evaluate()` returning `None` (not raising — this keeps parity_test.py check 6 happy). `get_default_config()` returning a TemplateConfig. `README.md` with step-by-step guide: copy folder, rename classes, implement evaluate, test. Include inline doc comments in strategy.py explaining each section the developer must customize.
  - Verify: `cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; d = discover_strategies(); assert 'TEMPLATE' in d; print(sorted(d.keys()))"` discovers TEMPLATE; `cd src && PYTHONPATH=. python3 scripts/parity_test.py` passes (check 6 auto-tests TEMPLATE)
  - Done when: TEMPLATE folder has 4 files, registry discovers it, evaluate() returns None on any input, all existing verification scripts pass

- [x] **T02: Build parameter optimization script with grid-search CLI** `est:30m`
  - Why: Delivers R012 — systematic parameter search replaces manual tuning. Also adds `get_param_grid()` to S1 and S2 configs to define their search spaces.
  - Files: `src/analysis/optimize.py`, `src/shared/strategies/S1/config.py`, `src/shared/strategies/S2/config.py`
  - Do: (1) Add `get_param_grid() -> dict[str, list]` to S1 config (2-3 key params, 3-4 values each — keep grid small). (2) Same for S2 config. (3) Create `analysis/optimize.py` with CLI (`--strategy`, `--dry-run`, `--output-dir`). The optimizer: discovers strategies via registry, dynamically imports `get_param_grid` from the strategy's config module, generates Cartesian product with `itertools.product`, instantiates strategy class with custom config per combo, calls `run_strategy()` from `backtest_strategies`, collects all metrics into a DataFrame, applies `add_ranking_score()`, saves results via `save_module_results()`. Must skip TEMPLATE and strategies without `get_param_grid()`. `--dry-run` prints grid and combo count then exits. Handle edge case where only 1 combo exists (add_ranking_score needs >0 rows but handles 1 row fine since it uses rank(pct=True)).
  - Verify: `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` prints grid and combo count; `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid())"` returns non-empty dict; all existing verification scripts pass
  - Done when: `--dry-run` works for S1 and S2, optimizer module is importable, get_param_grid exists for both strategies, no regressions

## Files Likely Touched

- `src/shared/strategies/TEMPLATE/__init__.py` (new)
- `src/shared/strategies/TEMPLATE/config.py` (new)
- `src/shared/strategies/TEMPLATE/strategy.py` (new)
- `src/shared/strategies/TEMPLATE/README.md` (new)
- `src/analysis/optimize.py` (new)
- `src/shared/strategies/S1/config.py` (add get_param_grid)
- `src/shared/strategies/S2/config.py` (add get_param_grid)
gy S1 --dry-run` prints grid and combo count; `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid())"` returns non-empty dict; all existing verification scripts pass
  - Done when: `--dry-run` works for S1 and S2, optimizer module is importable, get_param_grid exists for both strategies, no regressions

## Files Likely Touched

- `src/shared/strategies/TEMPLATE/__init__.py` (new)
- `src/shared/strategies/TEMPLATE/config.py` (new)
- `src/shared/strategies/TEMPLATE/strategy.py` (new)
- `src/shared/strategies/TEMPLATE/README.md` (new)
- `src/analysis/optimize.py` (new)
- `src/shared/strategies/S1/config.py` (add get_param_grid)
- `src/shared/strategies/S2/config.py` (add get_param_grid)
