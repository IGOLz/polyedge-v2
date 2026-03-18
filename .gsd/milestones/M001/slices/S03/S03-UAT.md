# S03: Trading adapter — live signals through shared strategies — UAT

**Milestone:** M001
**Written:** 2026-03-18

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: S03 is contract-verified with synthetic data. Real runtime testing (live ticks, DB, async executor) is deferred to S04 parity verification. The adapter is a composition of proven components (shared strategies from S01, existing trading infrastructure) — contract verification confirms the wiring is correct.

## Preconditions

- Working directory: `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M001`
- Python 3 available with numpy installed
- Symlinks from main repo's `src/trading/*.py` and `src/shared/db.py` are in place (created during T01)
- No external services required (all deps mocked in verification scripts)

## Smoke Test

```bash
cd src && PYTHONPATH=. python3 scripts/verify_s03.py
```
Exit code 0 with "18 passed, 0 failed" — confirms full adapter pipeline works.

## Test Cases

### 1. Import chain resolves cleanly

1. `cd src && PYTHONPATH=. python3 -c "import sys; from unittest.mock import MagicMock; [sys.modules.update({k: MagicMock()}) for k in ['py_clob_client','py_clob_client.client','py_clob_client.clob_types','trading.config','shared.db','colorama']]; from trading.strategy_adapter import evaluate_strategies, ticks_to_snapshot; print('OK')"`
2. **Expected:** Prints `OK` with exit code 0. Both `evaluate_strategies` and `ticks_to_snapshot` are importable.

### 2. main.py uses shared adapter import

1. `grep "from trading.strategy_adapter import evaluate_strategies" src/trading/main.py`
2. **Expected:** Exactly 1 match at line 20.
3. `grep "from trading.strategies import evaluate_strategies" src/trading/main.py`
4. **Expected:** 0 matches (old import removed).

### 3. Tick-to-snapshot produces correct numpy array

1. Run verify_s03.py checks 4-7
2. **Expected:** MarketSnapshot.prices has shape `(total_seconds,)`, NaN at seconds with no tick data (e.g. second 5), correct float values at seconds with ticks (s=0→0.50, s=10→0.60, s=100→0.48).

### 4. S1 strategy fires on calibrated spike data

1. Run verify_s03.py checks 8-10
2. **Expected:** `get_strategy('S1').evaluate(spike_snapshot)` returns a non-None Signal with `direction='Down'` (contrarian to up-spike) and `signal_data` containing `reversion_second` key.

### 5. Executor-required fields fully populated

1. Run verify_s03.py checks 11-14
2. **Expected:** Signal has `locked_shares > 0`, `locked_cost > 0`, `signal_data` contains `price_min`, `price_max`, `profitability_thesis` (non-empty string), `bet_cost`, `shares`, `stop_loss_price`, `balance_at_signal`, `seconds_elapsed`, `seconds_remaining`.

### 6. evaluate_strategies is async

1. `cd src && PYTHONPATH=. python3 -c "import sys; from unittest.mock import MagicMock; [sys.modules.update({k: MagicMock()}) for k in ['py_clob_client','py_clob_client.client','py_clob_client.clob_types','trading.config','shared.db','colorama']]; import inspect; from trading.strategy_adapter import evaluate_strategies; assert inspect.iscoroutinefunction(evaluate_strategies); print('async: OK')"`
2. **Expected:** Prints `async: OK` — confirms drop-in signature compatibility with old `trading.strategies.evaluate_strategies`.

### 7. R009 file integrity — executor, redeemer, balance unchanged

1. Run verify_s03.py checks 16-17
2. **Expected:** SHA-256 hashes of `trading/executor.py`, `trading/redeemer.py`, and `trading/balance.py` match the originals at `/Users/igol/Documents/repo/polyedge/src/trading/`.

## Edge Cases

### Empty ticks (fewer than 2)

1. Run verify_s03.py check 15
2. **Expected:** `ticks_to_snapshot(market, [])` returns MarketSnapshot with all-NaN prices array. No crash, no exception.

### Bet-too-large guard

1. In T01 verification: `_populate_execution_fields()` returns `None` when `actual_cost > balance * max_single_trade_pct`
2. **Expected:** Signal is silently dropped with debug_log message, not added to results list.

### Module isolation — no cross-domain imports

1. Run verify_s03.py check 18 (AST parse of strategy_adapter.py)
2. **Expected:** No `analysis.*` or `core.*` imports found. Adapter only imports from `shared.strategies`, `trading.*`.

## Failure Signals

- `verify_s03.py` exits with code 1 and prints `FAIL` for specific check(s)
- `grep` finds old import `from trading.strategies import evaluate_strategies` still in main.py
- Hash mismatch on executor.py/redeemer.py/balance.py (R009 violation)
- Import errors when loading `trading.strategy_adapter` (broken symlinks or missing mocks)

## Requirements Proved By This UAT

- R006 — Trading converts live tick streams to MarketSnapshot, runs shared strategy evaluate, produces executor-compatible Signal objects. Proven by checks 1-14 of verify_s03.py.
- R009 — Executor, redeemer, balance unchanged. Proven by hash integrity checks 16-17.
- R001 (partial) — S1 consumed by trading adapter via shared registry, same as analysis adapter. Full parity deferred to S04.
- R003 (partial) — Trading produces MarketSnapshot indexed by elapsed seconds. Full parity with analysis deferred to S04.

## Not Proven By This UAT

- R007 — Same config + same data → identical signals across both adapters (requires S04 parity test)
- Live async runtime behavior (event loop, DB pool, real balance fetch)
- Interaction with real executor order placement
- Multi-strategy concurrent evaluation with real already-traded DB checks
- Docker deployment compatibility

## Notes for Tester

- All verification uses mocked `py_clob_client` — the third-party trading SDK is not installed in the dev Python environment. This is expected and documented in KNOWLEDGE.md.
- Symlinks to main repo modules are required for imports to resolve. If checks fail with `ModuleNotFoundError`, verify symlinks exist: `ls -la src/trading/balance.py src/trading/db.py src/trading/constants.py src/shared/db.py`.
- The profitability thesis string (check 14) is dynamically constructed — exact wording may vary but should be non-empty and contain strategy name + price info.
- S1 synthetic data uses the calibration from KNOWLEDGE.md: spike peak at s=4 (0.85), reversion to 0.75 by s=11. If S1's thresholds change, the test data may need recalibration.
