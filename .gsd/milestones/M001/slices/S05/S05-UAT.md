# S05: Strategy template + parameter optimization — UAT

**Milestone:** M001
**Written:** 2026-03-18

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: TEMPLATE is a static skeleton (no runtime behavior beyond returning None), and the optimizer's dry-run mode validates the full CLI and grid logic without requiring a live database. All verification can be done via Python imports and CLI invocations.

## Preconditions

- Working directory: `src/` under the project root
- Python 3.10+ with numpy and pandas available
- `PYTHONPATH=.` set (all commands below assume `cd src && PYTHONPATH=.`)
- No database connection required (all tests use synthetic data or dry-run mode)

## Smoke Test

```bash
cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; print(sorted(discover_strategies().keys()))"
```
**Expected:** `['S1', 'S2', 'TEMPLATE']` — all three strategies discovered.

## Test Cases

### 1. TEMPLATE imports cleanly

1. Run: `python3 -c "from shared.strategies.TEMPLATE.strategy import TemplateStrategy; from shared.strategies.TEMPLATE.config import get_default_config; s = TemplateStrategy(get_default_config()); print('OK')"`
2. **Expected:** Prints `OK`, exit code 0. No import errors.

### 2. TEMPLATE evaluate() returns None (safe no-op)

1. Run:
   ```bash
   python3 -c "
   from shared.strategies.TEMPLATE.config import get_default_config
   from shared.strategies.TEMPLATE.strategy import TemplateStrategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   s = TemplateStrategy(get_default_config())
   r = s.evaluate(MarketSnapshot(market_id='test', market_type='test', prices=np.array([0.5]*60), total_seconds=60, elapsed_seconds=60))
   assert r is None, f'Expected None, got {r}'
   print('evaluate() returns None: OK')
   "
   ```
2. **Expected:** Prints `evaluate() returns None: OK`. Does NOT raise NotImplementedError.

### 3. Registry discovers TEMPLATE alongside S1 and S2

1. Run: `python3 -c "from shared.strategies.registry import discover_strategies; d = discover_strategies(); assert 'TEMPLATE' in d and 'S1' in d and 'S2' in d; print('All discovered:', sorted(d.keys()))"`
2. **Expected:** `All discovered: ['S1', 'S2', 'TEMPLATE']`

### 4. TEMPLATE has all four required files

1. Run: `ls -1 shared/strategies/TEMPLATE/`
2. **Expected:** Output contains exactly: `__init__.py`, `config.py`, `strategy.py`, `README.md`

### 5. TEMPLATE README exists and has content

1. Run: `wc -l shared/strategies/TEMPLATE/README.md`
2. **Expected:** At least 20 lines of documentation (step-by-step guide).

### 6. S1 has get_param_grid() with non-empty search space

1. Run: `python3 -c "from shared.strategies.S1.config import get_param_grid; g = get_param_grid(); assert len(g) > 0; print('S1 grid:', g)"`
2. **Expected:** Prints dict with at least 2 parameters, each having 2+ values. E.g.: `{'spike_threshold_up': [0.75, 0.8, 0.85], 'reversion_reversal_pct': [0.08, 0.1, 0.12], 'entry_price_threshold': [0.3, 0.35, 0.4]}`

### 7. S2 has get_param_grid() with non-empty search space

1. Run: `python3 -c "from shared.strategies.S2.config import get_param_grid; g = get_param_grid(); assert len(g) > 0; print('S2 grid:', g)"`
2. **Expected:** Prints dict with at least 2 parameters, each having 2+ values. E.g.: `{'volatility_threshold': [0.03, 0.05, 0.07], 'min_spread': [0.03, 0.05, 0.07], 'base_deviation': [0.06, 0.08, 0.1]}`

### 8. Optimizer dry-run for S1 prints grid and exits cleanly

1. Run: `python3 -m analysis.optimize --strategy S1 --dry-run`
2. **Expected:** Output contains:
   - `Grid-Search Optimization: S1`
   - Parameter names and value lists
   - `Total combinations: 27`
   - `[dry-run] Exiting without running backtests.`
   - Exit code 0

### 9. Optimizer dry-run for S2 prints grid and exits cleanly

1. Run: `python3 -m analysis.optimize --strategy S2 --dry-run`
2. **Expected:** Output contains:
   - `Grid-Search Optimization: S2`
   - Parameter names and value lists
   - `Total combinations: 27`
   - `[dry-run] Exiting without running backtests.`
   - Exit code 0

### 10. Parity test regression — all checks still pass

1. Run: `python3 scripts/parity_test.py`
2. **Expected:** `24 passed, 0 failed` — including check 6 which auto-tests TEMPLATE.

### 11. S01 verification regression

1. Run: `python3 scripts/verify_s01.py`
2. **Expected:** All checks pass (17/17).

### 12. S02 verification regression

1. Run: `python3 scripts/verify_s02.py`
2. **Expected:** All checks pass (18/18).

## Edge Cases

### Optimizer rejects TEMPLATE strategy

1. Run: `python3 -m analysis.optimize --strategy TEMPLATE --dry-run`
2. **Expected:** Prints error message containing `"Cannot optimize TEMPLATE"` or similar, exit code 1. Does NOT attempt grid-search on TEMPLATE.

### Optimizer rejects nonexistent strategy

1. Run: `python3 -m analysis.optimize --strategy NONEXISTENT --dry-run`
2. **Expected:** Prints error message listing available strategies (S1, S2), exit code 1.

### TEMPLATE config has expected structure

1. Run: `python3 -c "from shared.strategies.TEMPLATE.config import get_default_config; c = get_default_config(); assert c.strategy_id == 'TEMPLATE'; print(f'id={c.strategy_id}, name={c.strategy_name}')"`
2. **Expected:** Prints `id=TEMPLATE, name=TEMPLATE_strategy` — config follows convention.

## Failure Signals

- TEMPLATE missing from `discover_strategies()` output → import error in TEMPLATE folder; run `python3 -c "from shared.strategies.TEMPLATE.strategy import TemplateStrategy"` to see traceback
- `evaluate()` raises instead of returning None → breaks parity_test.py check 6 and any pipeline that auto-evaluates all strategies
- `get_param_grid()` missing from S1/S2 config → optimizer skips with message `"Strategy X has no get_param_grid() — skipping"`
- Optimizer dry-run prints 0 combinations → `get_param_grid()` returns empty dict
- parity_test.py check count drops below 24 → regression in strategy framework

## Requirements Proved By This UAT

- R011 — TEMPLATE folder exists with 4 files, is auto-discovered, evaluate() returns None safely, README provides creation guide
- R012 — Optimizer CLI works in dry-run mode, param grids defined for S1 and S2, TEMPLATE and strategies without grids are skipped

## Not Proven By This UAT

- Full optimizer run with actual DB data (requires populated TimescaleDB) — only dry-run mode verified
- End-to-end experience of creating a new strategy from TEMPLATE (human-experience UAT would be needed)
- Optimizer result quality — ranking correctness depends on backtest data and engine internals, not testable without real markets

## Notes for Tester

- All commands assume `cd src && PYTHONPATH=.` — this is the standard invocation pattern for the project.
- The optimizer's non-dry-run mode requires a running TimescaleDB with historical data. If you want to test it, ensure the DB is populated via core's data collection first.
- TEMPLATE's README is the authoritative guide for creating new strategies — reading it end-to-end is the best way to validate R011's "developer experience" intent.
- The parity test now runs 24 checks (was 23 before S05) because check 6 auto-includes TEMPLATE.
