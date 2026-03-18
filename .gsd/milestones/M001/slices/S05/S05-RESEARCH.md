# S05 — Strategy template + parameter optimization — Research

**Date:** 2026-03-18
**Depth:** Light — both deliverables follow established patterns with no unknowns.

## Summary

S05 delivers two independent pieces: a TEMPLATE strategy folder (R011) and a parameter optimization script (R012). Both are straightforward.

The TEMPLATE folder is a copy of the proven S1/S2 directory structure (`__init__.py`, `config.py`, `strategy.py`) with placeholder logic and inline documentation. The developer copies it, renames class/config, implements `evaluate()`, and the registry auto-discovers it. No framework changes needed.

The optimization script (`analysis/optimize.py`) is a grid-search wrapper around the existing `backtest_strategies.run_strategy()` function. It takes a strategy ID, generates parameter combinations from a search space defined per-strategy in config, runs each through the existing backtest pipeline, and ranks results using the existing `add_ranking_score()` engine function. The key design choice: each strategy's config module exposes an optional `get_param_grid() -> dict[str, list]` function that maps config field names to lists of candidate values. `itertools.product` produces the Cartesian product. No external optimization libraries needed — the backtest engine already computes all the metrics and ranking.

## Recommendation

Build in two independent tasks:

1. **T01: TEMPLATE folder** — Copy S1 structure, replace logic with documented placeholders, add a README.md inside the folder explaining how to create a new strategy. Concrete class with `evaluate()` raising `NotImplementedError` so the registry discovers it but it fails clearly if someone tries to run it without implementing.

2. **T02: Optimization script** — New `src/analysis/optimize.py` module (runnable as `python -m analysis.optimize --strategy S1`). Add `get_param_grid()` to S1 and S2 config modules. Reuse `backtest_strategies.run_strategy()` and `engine.add_ranking_score()` for evaluation and ranking.

These two tasks have zero dependency on each other and can be built/verified independently.

## Implementation Landscape

### Key Files

- `src/shared/strategies/TEMPLATE/__init__.py` — empty, same as S1/S2 (to create)
- `src/shared/strategies/TEMPLATE/config.py` — skeleton TemplateConfig(StrategyConfig) with example fields + `get_default_config()` + `get_param_grid()` (to create)
- `src/shared/strategies/TEMPLATE/strategy.py` — skeleton TemplateStrategy(BaseStrategy) with `evaluate()` raising NotImplementedError and inline doc comments (to create)
- `src/shared/strategies/TEMPLATE/README.md` — step-by-step guide for creating a new strategy (to create)
- `src/analysis/optimize.py` — grid-search optimizer module with CLI (to create)
- `src/shared/strategies/S1/config.py` — add `get_param_grid()` returning search ranges for S1 params (to modify)
- `src/shared/strategies/S2/config.py` — add `get_param_grid()` returning search ranges for S2 params (to modify)
- `src/analysis/backtest_strategies.py` — used by optimizer but NOT modified; `run_strategy()` is called directly (read-only)
- `src/analysis/backtest/engine.py` — `compute_metrics()`, `add_ranking_score()` used by optimizer (read-only)
- `src/shared/strategies/registry.py` — registry discovers TEMPLATE folder; the `try/except` handles it gracefully since the class is concrete (read-only)
- `src/shared/strategies/base.py` — `StrategyConfig`, `BaseStrategy`, `MarketSnapshot`, `Signal` — no changes needed (read-only)

### Build Order

**T01 (TEMPLATE) and T02 (optimizer) are independent — can be built in any order or parallel.**

T01 is simpler (4 files, all new, ~100 lines total). T02 is the meatier piece (~150-200 lines) but uses only existing infrastructure.

For T02, the critical insight: the optimizer instantiates strategy classes directly (not via `get_strategy()`) because it needs to pass custom configs. Pattern:

```python
from shared.strategies.registry import discover_strategies
from shared.strategies.S1.config import S1Config, get_param_grid

strategy_cls = discover_strategies()['S1']
for param_combo in itertools.product(*grid.values()):
    config = S1Config(strategy_id='S1', strategy_name='S1_spike_reversion', **dict(zip(grid.keys(), param_combo)))
    strategy = strategy_cls(config)
    trades, metrics = run_strategy(config_label, strategy, markets)
```

The optimizer needs to dynamically import `get_param_grid` from each strategy's config module. Use `importlib.import_module(f"shared.strategies.{sid}.config")` — same pattern `registry.get_strategy()` already uses.

### Verification Approach

**T01 verification:**
1. `ls src/shared/strategies/TEMPLATE/` — 4 files exist (`__init__.py`, `config.py`, `strategy.py`, `README.md`)
2. `PYTHONPATH=. python3 -c "from shared.strategies.TEMPLATE.strategy import TemplateStrategy; from shared.strategies.TEMPLATE.config import get_default_config; s = TemplateStrategy(get_default_config()); print('OK')"` — imports cleanly
3. `PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; d = discover_strategies(); assert 'TEMPLATE' in d; print('Discovered:', sorted(d.keys()))"` — registry sees it
4. Existing scripts still pass: `python3 scripts/verify_s01.py`, `python3 scripts/verify_s02.py`, `python3 scripts/parity_test.py` — no regressions

**T02 verification:**
1. `PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` — prints parameter grid and combination count without running backtests
2. Integration test with actual data requires DB (optional for verification script; recommend a `--dry-run` flag)
3. Verify `get_param_grid()` exists for S1 and S2: `PYTHONPATH=. python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid())"`
4. Existing scripts still pass (same as T01 regression check)

**Slice-level acceptance (from roadmap):**
- `shared/strategies/TEMPLATE/` exists with documented skeleton ✓
- `python -m analysis.optimize --strategy S1` grid-searches the config space and ranks parameter combinations ✓

## Constraints

- Strategy configs are dataclasses — all fields have defaults, so constructing with `S1Config(strategy_id='S1', strategy_name='S1_spike_reversion', spike_threshold_up=0.75)` overrides just the specified field. This makes grid-search param injection trivial.
- The optimizer MUST NOT modify `backtest_strategies.py` or `engine.py` — it imports and calls their functions.
- `get_param_grid()` is optional per strategy. The optimizer should gracefully handle strategies that don't define it (skip with a message or use single-value defaults).
- The TEMPLATE folder will be auto-discovered by `discover_strategies()`. This is fine — `get_strategy('TEMPLATE')` would instantiate it, but `evaluate()` raises `NotImplementedError`. The optimizer should skip TEMPLATE if it appears in the registry.
- `add_ranking_score()` needs >1 row in the DataFrame to compute percentiles. The optimizer should handle the edge case where only 1 param combo is tested.

## Common Pitfalls

- **TEMPLATE polluting registry** — `discover_strategies()` will include TEMPLATE. Parity test check 6 ("multi-strategy consistency") auto-tests all discovered strategies. The template's `NotImplementedError` in `evaluate()` would cause check 6 to fail. **Fix:** Either (a) the parity test catches `NotImplementedError` and skips, or (b) TEMPLATE's evaluate returns `None` instead of raising. Option (b) is cleaner — returning `None` means "no signal", which is valid behavior and won't break any consumer. The README can document that the developer must replace the `return None` placeholder.
- **Grid explosion** — `itertools.product` with many params × many values grows fast. S1 has 6 tunable params, S2 has 6. If each has 5 values: 5^6 = 15,625 combos. Each combo runs against all markets. **Fix:** Keep default grids small (3-4 values per param, 2-3 key params only). Document that users can customize the grid.
