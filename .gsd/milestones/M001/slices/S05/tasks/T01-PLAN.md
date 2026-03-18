---
estimated_steps: 5
estimated_files: 4
---

# T01: Create TEMPLATE strategy folder with documented skeleton

**Slice:** S05 — Strategy template + parameter optimization
**Milestone:** M001

## Description

Create `shared/strategies/TEMPLATE/` with four files that follow the exact S1/S2 directory pattern. This is the copy-and-customize starting point for new strategies (R011). The TEMPLATE must be auto-discovered by `discover_strategies()`, and its `evaluate()` must return `None` (not raise `NotImplementedError`) — this ensures parity_test.py check 6 (which auto-tests all discovered strategies) continues to pass.

**Relevant skills:** None required — pure Python file creation following established patterns.

## Steps

1. Create `src/shared/strategies/TEMPLATE/__init__.py` — empty file (same as S1/S2).

2. Create `src/shared/strategies/TEMPLATE/config.py` with:
   - `TemplateConfig(StrategyConfig)` dataclass with 2-3 example fields (e.g. `example_threshold: float = 0.50`, `example_window_seconds: int = 30`) and sensible defaults
   - `get_default_config()` returning `TemplateConfig(strategy_id="TEMPLATE", strategy_name="TEMPLATE_strategy")`
   - Clear docstrings explaining that the developer should rename the class and replace fields with their strategy's parameters
   - Follow the exact import and structure pattern of `S1/config.py`

3. Create `src/shared/strategies/TEMPLATE/strategy.py` with:
   - `TemplateStrategy(BaseStrategy)` class
   - `evaluate(self, snapshot: MarketSnapshot) -> Signal | None` that returns `None` — this is the placeholder, NOT `NotImplementedError`
   - Inline `# TODO:` comments at each section the developer must customize: guard checks, signal detection logic, Signal construction
   - Module docstring explaining this is a template to be copied
   - Follow the exact import pattern of `S1/strategy.py`: `from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal` and `from shared.strategies.TEMPLATE.config import TemplateConfig`

4. Create `src/shared/strategies/TEMPLATE/README.md` with a step-by-step guide:
   - How to create a new strategy (copy TEMPLATE folder, rename to S3/S4/etc.)
   - Rename `TemplateConfig` → `S3Config`, `TemplateStrategy` → `S3Strategy`
   - Update `strategy_id` and `strategy_name` in `get_default_config()`
   - Replace example fields in config with real parameters
   - Implement `evaluate()` — explain the contract: pure function, return Signal or None, no side effects
   - Mention optional `get_param_grid()` for parameter optimization
   - Note that `discover_strategies()` auto-discovers by folder name — no registration needed
   - Note that new strategies should use `entry_second` as the canonical key in `signal_data` (per D010)

5. Verify:
   - `cd src && PYTHONPATH=. python3 -c "from shared.strategies.TEMPLATE.strategy import TemplateStrategy; from shared.strategies.TEMPLATE.config import get_default_config; s = TemplateStrategy(get_default_config()); print('Import OK')"` — imports work
   - `cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; d = discover_strategies(); assert 'TEMPLATE' in d; assert 'S1' in d; assert 'S2' in d; print('Discovered:', sorted(d.keys()))"` — registry sees all three
   - `cd src && PYTHONPATH=. python3 -c "from shared.strategies.TEMPLATE.config import get_default_config; from shared.strategies.TEMPLATE.strategy import TemplateStrategy; s = TemplateStrategy(get_default_config()); from shared.strategies.base import MarketSnapshot; import numpy as np; r = s.evaluate(MarketSnapshot(market_id='t', market_type='t', prices=np.array([0.5]*60), total_seconds=60, elapsed_seconds=60)); assert r is None; print('evaluate returns None: OK')"` — safe no-op
   - `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — all checks pass (check 6 auto-tests TEMPLATE)
   - `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — no regressions
   - `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — no regressions

## Must-Haves

- [ ] `TEMPLATE/__init__.py` exists (empty)
- [ ] `TEMPLATE/config.py` has `TemplateConfig(StrategyConfig)` dataclass with example fields and `get_default_config()`
- [ ] `TEMPLATE/strategy.py` has `TemplateStrategy(BaseStrategy)` with `evaluate()` returning `None`
- [ ] `TEMPLATE/README.md` has step-by-step guide for creating a new strategy
- [ ] `discover_strategies()` includes `'TEMPLATE'` in its result
- [ ] `parity_test.py` passes (TEMPLATE's None return doesn't break check 6)
- [ ] `verify_s01.py` and `verify_s02.py` pass (no regressions)

## Verification

- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; d = discover_strategies(); assert 'TEMPLATE' in d; print('OK')"` — TEMPLATE discovered
- `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — exit code 0
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — exit code 0
- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — exit code 0

## Observability Impact

- **New inspection surface:** `discover_strategies()` now returns `'TEMPLATE'` in its result dict. This confirms the template folder is correctly structured for auto-discovery.
- **Failure visibility:** If the TEMPLATE module has import errors, `discover_strategies()` silently skips it. Diagnose with `python3 -c "from shared.strategies.TEMPLATE.strategy import TemplateStrategy"` to get the traceback.
- **Regression signal:** `parity_test.py` check 6 auto-evaluates all discovered strategies — a broken TEMPLATE evaluate() will show as a check-6 failure with strategy name in the output.
- **No new logs or metrics:** TEMPLATE is a passive skeleton; it produces no runtime output until a developer implements evaluate().

## Inputs

- `src/shared/strategies/S1/` — reference pattern for directory structure, config.py, strategy.py, __init__.py
- `src/shared/strategies/S2/` — second reference confirming the pattern
- `src/shared/strategies/base.py` — `StrategyConfig`, `BaseStrategy`, `MarketSnapshot`, `Signal` interfaces
- `src/shared/strategies/registry.py` — `discover_strategies()` scans `*/strategy.py` for `BaseStrategy` subclasses
- D010 — new strategies should use `entry_second` as canonical key in signal_data

## Expected Output

- `src/shared/strategies/TEMPLATE/__init__.py` — empty init for auto-discovery
- `src/shared/strategies/TEMPLATE/config.py` — TemplateConfig dataclass with example fields + get_default_config()
- `src/shared/strategies/TEMPLATE/strategy.py` — TemplateStrategy with evaluate() returning None + inline TODO comments
- `src/shared/strategies/TEMPLATE/README.md` — developer guide for creating new strategies
