---
id: T01
parent: S05
milestone: M001
provides:
  - TEMPLATE strategy folder with documented skeleton for creating new strategies (R011)
key_files:
  - src/shared/strategies/TEMPLATE/__init__.py
  - src/shared/strategies/TEMPLATE/config.py
  - src/shared/strategies/TEMPLATE/strategy.py
  - src/shared/strategies/TEMPLATE/README.md
key_decisions:
  - D011 — evaluate() returns None instead of raising NotImplementedError (parity_test safety)
patterns_established:
  - TEMPLATE folder as copy-and-customize starting point for new strategies
  - entry_second as canonical signal_data key documented in README (per D010)
observability_surfaces:
  - discover_strategies() includes TEMPLATE in returned dict — absence means import failure
  - parity_test.py check 6 auto-tests TEMPLATE — regression-visible if evaluate() breaks
duration: 8m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T01: Create TEMPLATE strategy folder with documented skeleton

**Added TEMPLATE strategy skeleton with 4 files matching S1/S2 pattern — auto-discovered by registry, evaluate() returns None safely, README guides new strategy creation**

## What Happened

Created `src/shared/strategies/TEMPLATE/` with four files following the established S1/S2 directory pattern:

1. `__init__.py` — empty, required for Python package discovery.
2. `config.py` — `TemplateConfig(StrategyConfig)` dataclass with three example fields (`example_threshold`, `example_window_seconds`, `example_min_spread`) and `get_default_config()` returning `TemplateConfig(strategy_id="TEMPLATE", strategy_name="TEMPLATE_strategy")`. Docstrings explain what to rename and replace.
3. `strategy.py` — `TemplateStrategy(BaseStrategy)` with `evaluate()` returning `None`. Three inline `# TODO:` sections guide the developer through guard checks, signal detection, and Signal construction. The Signal construction example includes `entry_second` as the canonical key per D010.
4. `README.md` — Step-by-step guide: copy folder → rename classes → update config → implement evaluate → optional `get_param_grid()` → verify. Documents the evaluate() contract, `entry_second` convention, and auto-discovery mechanism.

Also added missing observability sections to S05-PLAN.md and T01-PLAN.md per pre-flight requirements, and added a diagnostic verification step to the slice plan.

## Verification

- Direct import of `TemplateStrategy` and `get_default_config()` — OK
- `discover_strategies()` returns `['S1', 'S2', 'TEMPLATE']` — all three discovered
- `evaluate()` on flat prices returns `None` (not raise) — safe no-op confirmed
- `parity_test.py` — 24/24 checks pass, including check 6 which auto-tests TEMPLATE
- `verify_s01.py` — 17/17 checks pass, no regressions
- `verify_s02.py` — 18/18 checks pass, no regressions
- Diagnostic registry completeness check — all strategies discoverable

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python3 -c "...TemplateStrategy...print('Import OK')"` | 0 | ✅ pass | <1s |
| 2 | `python3 -c "...discover_strategies()...assert 'TEMPLATE' in d..."` | 0 | ✅ pass | <1s |
| 3 | `python3 -c "...evaluate(...)...assert r is None..."` | 0 | ✅ pass | <1s |
| 4 | `python3 scripts/parity_test.py` | 0 | ✅ pass | 3s |
| 5 | `python3 scripts/verify_s01.py` | 0 | ✅ pass | 3s |
| 6 | `python3 scripts/verify_s02.py` | 0 | ✅ pass | 3s |
| 7 | `python3 -c "...missing = [s for s in ['S1','S2','TEMPLATE'] if s not in d]..."` | 0 | ✅ pass | <1s |

## Diagnostics

- **Registry inspection:** `cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; print(sorted(discover_strategies().keys()))"` — should show `['S1', 'S2', 'TEMPLATE']`.
- **Import failure diagnosis:** If TEMPLATE disappears from registry, run `python3 -c "from shared.strategies.TEMPLATE.strategy import TemplateStrategy"` to surface the traceback.
- **Regression signal:** parity_test.py check 6 auto-evaluates TEMPLATE — a broken evaluate() shows as check-6 failure.

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/shared/strategies/TEMPLATE/__init__.py` — empty init for package discovery
- `src/shared/strategies/TEMPLATE/config.py` — TemplateConfig dataclass with example fields + get_default_config()
- `src/shared/strategies/TEMPLATE/strategy.py` — TemplateStrategy with evaluate() returning None + inline TODO comments
- `src/shared/strategies/TEMPLATE/README.md` — developer guide for creating new strategies
- `.gsd/milestones/M001/slices/S05/S05-PLAN.md` — added observability section, diagnostic verification step, marked T01 done
- `.gsd/milestones/M001/slices/S05/tasks/T01-PLAN.md` — added observability impact section
