# S02: Analysis adapter — backtest through shared strategies — UAT

**Milestone:** M001
**Written:** 2026-03-18

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: The adapter is a data pipeline (market dict → MarketSnapshot → Signal → Trade → metrics). All stages are verifiable with synthetic data and inspectable output artifacts. No UI, no external services (beyond optional DB for full integration).

## Preconditions

- Working directory: `cd src` within the repository
- `PYTHONPATH=.` set (or run from `src/` with module syntax)
- Python 3.10+ with numpy and pandas installed
- `shared/strategies/S1/` exists (from S01)
- No database required for contract tests (DB required only for full integration test case 5)

## Smoke Test

```bash
cd src && PYTHONPATH=. python3 scripts/verify_s02.py
```
Expected: 18/18 checks pass, exit code 0. If this passes, the adapter pipeline is fundamentally working.

## Test Cases

### 1. Contract verification — full pipeline on synthetic data

1. Run `cd src && PYTHONPATH=. python3 scripts/verify_s02.py`
2. **Expected:** All 18 checks show `[PASS]`, summary line reads `18 passed, 0 failed`, exit code 0

### 2. CLI help — module integrity

1. Run `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --help`
2. **Expected:** Usage output shows four flags: `-s/--strategy`, `-o/--output-dir`, `--assets`, `--durations`. No import errors or tracebacks.

### 3. Empty market list — graceful zero-trade handling

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import run_strategy
   from shared.strategies import get_strategy
   s = get_strategy('S1')
   trades, metrics = run_strategy('S1', s, [])
   assert metrics['total_bets'] == 0
   assert len(trades) == 0
   print('OK: zero markets → zero trades, no error')
   "
   ```
2. **Expected:** Prints `[S1] Evaluating 0 markets → 0 trades` then `OK: zero markets → zero trades, no error`. Exit code 0.

### 4. Importability — adapter functions accessible

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import market_to_snapshot, run_strategy, main
   print('market_to_snapshot:', callable(market_to_snapshot))
   print('run_strategy:', callable(run_strategy))
   print('main:', callable(main))
   "
   ```
2. **Expected:** All three print `True`. No import errors.

### 5. Full integration — real market data (requires DB)

1. Ensure TimescaleDB is running with market data populated
2. Run `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --output-dir /tmp/s02_test`
3. **Expected:**
   - Prints "Loading market data..."
   - Prints `[S1] Evaluating N markets → M trades` where N > 0
   - Prints summary line with bets, WR%, PnL, Sharpe, Score
   - `/tmp/s02_test/` contains: `Test_shared_strategies_Results.csv`, `shared_strategies_Best_Configs.txt`, `shared_strategies_Analysis.md`
   - CSV has at least one row with `config_id=S1` and `total_bets > 0`

### 6. Module isolation — no forbidden imports

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import ast, pathlib
   source = pathlib.Path('analysis/backtest_strategies.py').read_text()
   tree = ast.parse(source)
   forbidden = []
   for node in ast.walk(tree):
       if isinstance(node, (ast.Import, ast.ImportFrom)):
           module = getattr(node, 'module', '') or ''
           names = [a.name for a in node.names] if isinstance(node, ast.Import) else [module]
           for name in names:
               if name and any(name.startswith(p) for p in ('trading', 'core')):
                   forbidden.append(name)
   assert forbidden == [], f'Forbidden imports found: {forbidden}'
   print('OK: no trading.* or core.* imports')
   "
   ```
2. **Expected:** Prints `OK: no trading.* or core.* imports`. Exit code 0.

## Edge Cases

### Market with no signal (strategy returns None)

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import numpy as np
   from datetime import datetime, timezone
   from analysis.backtest_strategies import market_to_snapshot, run_strategy
   from shared.strategies import get_strategy
   # Flat prices — no spike, no signal
   flat_market = {
       'market_id': 'flat-001', 'market_type': 'BTC_5m', 'asset': 'BTC',
       'duration_minutes': 5, 'total_seconds': 300,
       'started_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
       'ended_at': datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
       'final_outcome': 'Up', 'hour': 12,
       'ticks': np.full(300, 0.50),
   }
   s = get_strategy('S1')
   trades, metrics = run_strategy('S1', s, [flat_market])
   assert len(trades) == 0
   assert metrics['total_bets'] == 0
   print('OK: flat market → no signal → no trade → total_bets=0')
   "
   ```
2. **Expected:** `[S1] Evaluating 1 markets → 0 trades` then `OK: flat market → no signal → no trade → total_bets=0`.

### Market with NaN-heavy price data

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import numpy as np
   from datetime import datetime, timezone
   from analysis.backtest_strategies import market_to_snapshot
   from shared.strategies import MarketSnapshot
   sparse_market = {
       'market_id': 'sparse-001', 'market_type': 'BTC_5m', 'asset': 'BTC',
       'duration_minutes': 5, 'total_seconds': 300,
       'started_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
       'ended_at': datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
       'final_outcome': 'Up', 'hour': 12,
       'ticks': np.full(300, np.nan),
   }
   snap = market_to_snapshot(sparse_market)
   assert isinstance(snap, MarketSnapshot)
   assert snap.prices.shape == (300,)
   print('OK: all-NaN market converts to MarketSnapshot without error')
   "
   ```
2. **Expected:** Prints `OK: all-NaN market converts to MarketSnapshot without error`. The conversion layer doesn't filter NaNs — that's the strategy's responsibility.

## Failure Signals

- `verify_s02.py` exits with code 1 — at least one pipeline stage is broken; first `[FAIL]` line identifies which
- `--help` produces an ImportError traceback — the adapter's import chain is broken (missing dependency file)
- `run_strategy` raises an exception instead of returning empty metrics for zero markets — error handling regression
- Any `trading.*` or `core.*` import found in the adapter — module isolation violated
- Integration test produces `total_bets=0` when real market data is loaded — Signal→Trade bridge may be misconfigured

## Requirements Proved By This UAT

- R005 — Test cases 1, 3, 4, and edge case "flat market" together prove: analysis converts data to MarketSnapshot, runs shared evaluate(), and collects backtest results. Contract-verified on synthetic data.
- R001 (partial, analysis side) — Test case 1 checks 9-11 prove the shared S1 strategy produces Signals when called through the analysis adapter. Trading side deferred to S03.
- R003 (partial, analysis side) — Test case 1 check 6 proves analysis produces MarketSnapshot with `elapsed_seconds` in seconds. Trading side deferred to S03.
- R010 — Test case 6 proves no `core.*` imports exist in the adapter.

## Not Proven By This UAT

- R005 full integration with real DB market data (test case 5 requires DB, optional)
- R006 — Trading adapter (S03)
- R007 — Parity between analysis and trading (S04)
- R009 — Executor/redeemer unchanged (S03)
- R012 — Optimization grid-search (S05, though run_strategy is the building block)

## Notes for Tester

- Test cases 1-4, 6, and both edge cases require no database — they run on synthetic data.
- Test case 5 is the only one requiring a live TimescaleDB with market data. Skip it if no DB is available; the contract tests cover the pipeline logic.
- The progress output `[S1] Evaluating N markets → M trades` appears on stdout during all run_strategy calls — this is expected diagnostic output, not an error.
- If test case 1 fails on check 9 (Signal is None), the most likely cause is S1 synthetic data calibration — see KNOWLEDGE.md for threshold details.
