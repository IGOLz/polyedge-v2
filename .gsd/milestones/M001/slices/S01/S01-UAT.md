# S01: Shared strategy framework + data model — UAT

**Milestone:** M001
**Written:** 2026-03-18

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: S01 produces importable Python modules and a verification script — no live runtime, database, or UI to interact with. All contracts can be validated by importing and calling functions.

## Preconditions

- Working directory: `src/` within the M001 worktree
- `PYTHONPATH=.` set (or run from `src/`)
- `python3` available with `numpy` installed
- No running services required

## Smoke Test

```bash
cd src && PYTHONPATH=. python3 -c "from shared.strategies import get_strategy; s = get_strategy('S1'); print(s.config.strategy_name)"
```
**Expected:** prints `S1_spike_reversion`

## Test Cases

### 1. Public API completeness

1. Run: `cd src && PYTHONPATH=. python3 -c "from shared.strategies import BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy; print('PASS')"`
2. **Expected:** prints `PASS` with exit code 0. All 6 names must be importable from the top-level package.

### 2. Registry discovers S1 strategy

1. Run: `cd src && PYTHONPATH=. python3 -c "from shared.strategies import discover_strategies; d = discover_strategies(); assert 'S1' in d; print(f'Found: {list(d.keys())}')"`
2. **Expected:** prints `Found: ['S1']`. Registry scans the S1 folder and finds S1Strategy.

### 3. S1 config has correct identity and parameters

1. Run:
```python
cd src && PYTHONPATH=. python3 -c "
from shared.strategies import get_strategy
s = get_strategy('S1')
assert s.config.strategy_id == 'S1'
assert s.config.strategy_name == 'S1_spike_reversion'
assert s.config.spike_detection_window_seconds == 15
assert s.config.spike_threshold_up == 0.80
assert s.config.entry_price_threshold == 0.35
print('config: PASS')
"
```
2. **Expected:** prints `config: PASS`. Config values match M3_CONFIG from trading constants.

### 4. Spike detection produces contrarian signal

1. Run:
```python
cd src && PYTHONPATH=. python3 -c "
import numpy as np
from shared.strategies import get_strategy, MarketSnapshot
s1 = get_strategy('S1')
prices = np.full(30, 0.5)
prices[2:5] = 0.85  # up-spike
prices[8:15] = 0.75  # partial reversion
snap = MarketSnapshot(market_id='test', market_type='binary', prices=prices, total_seconds=30, elapsed_seconds=30.0)
sig = s1.evaluate(snap)
assert sig is not None, 'Expected signal'
assert sig.direction == 'Down', f'Expected Down, got {sig.direction}'
assert sig.strategy_name == 'S1_spike_reversion'
assert 0 < sig.entry_price <= 0.35
print(f'Signal: {sig.direction} @ {sig.entry_price} — PASS')
"
```
2. **Expected:** prints signal with direction=Down and entry_price ≤ 0.35. Up-spike → contrarian Down signal.

### 5. Flat prices produce no signal

1. Run:
```python
cd src && PYTHONPATH=. python3 -c "
import numpy as np
from shared.strategies import get_strategy, MarketSnapshot
s1 = get_strategy('S1')
prices = np.full(30, 0.50)
snap = MarketSnapshot(market_id='test', market_type='binary', prices=prices, total_seconds=30, elapsed_seconds=30.0)
assert s1.evaluate(snap) is None
print('no-signal: PASS')
"
```
2. **Expected:** prints `no-signal: PASS`. Flat prices have no spike, so evaluate returns None.

### 6. Signal backward compatibility (executor fields)

1. Run:
```python
cd src && PYTHONPATH=. python3 -c "
from shared.strategies import Signal
s = Signal(direction='Up', strategy_name='test', entry_price=0.30)
assert s.locked_shares == 0
assert s.locked_cost == 0.0
assert s.locked_balance == 0.0
assert s.locked_bet_size == 0.0
assert s.signal_data == {}
assert s.confidence_multiplier == 1.0
assert s.created_at is not None
print('defaults: PASS')
"
```
2. **Expected:** prints `defaults: PASS`. All execution fields have safe defaults.

### 7. Full contract verification script

1. Run: `cd src && PYTHONPATH=. python3 scripts/verify_s01.py`
2. **Expected:** All 18 checks pass. Final line: `=== All S01 checks passed ===`

## Edge Cases

### NaN-heavy price data

1. Run:
```python
cd src && PYTHONPATH=. python3 -c "
import numpy as np
from shared.strategies import get_strategy, MarketSnapshot
s1 = get_strategy('S1')
prices = np.full(30, np.nan)
snap = MarketSnapshot(market_id='test', market_type='binary', prices=prices, total_seconds=30, elapsed_seconds=30.0)
assert s1.evaluate(snap) is None
print('all-NaN: PASS')
"
```
2. **Expected:** prints `all-NaN: PASS`. All-NaN data returns None without crashing.

### Short price array (fewer than detection window)

1. Run:
```python
cd src && PYTHONPATH=. python3 -c "
import numpy as np
from shared.strategies import get_strategy, MarketSnapshot
s1 = get_strategy('S1')
prices = np.array([0.5, 0.5, 0.5])  # only 3 seconds, window needs 15
snap = MarketSnapshot(market_id='test', market_type='binary', prices=prices, total_seconds=3, elapsed_seconds=3.0)
assert s1.evaluate(snap) is None
print('short-data: PASS')
"
```
2. **Expected:** prints `short-data: PASS`. Data shorter than spike_detection_window_seconds (15) returns None.

### Unknown strategy ID

1. Run:
```python
cd src && PYTHONPATH=. python3 -c "
from shared.strategies import get_strategy
try:
    get_strategy('NONEXISTENT')
    print('FAIL — no error raised')
except KeyError as e:
    assert 'Available' in str(e)
    print(f'error_path: PASS — {e}')
"
```
2. **Expected:** prints `error_path: PASS` with message listing available strategies.

### Import isolation

1. Run: `grep -r 'from trading\|from analysis\|from core' src/shared/strategies/ && echo 'FAIL: forbidden imports found' || echo 'isolation: PASS'`
2. **Expected:** prints `isolation: PASS`. No imports from trading, analysis, or core modules.

## Failure Signals

- Any import error from `shared.strategies` — indicates broken `__init__.py` or missing dependency
- `discover_strategies()` returns empty dict — PYTHONPATH not set or strategy.py has import error
- `get_strategy('S1')` raises AttributeError — missing `get_default_config()` in S1/config.py
- `evaluate()` raises instead of returning None — NaN handling regression
- Signal missing `locked_*` fields — base.py Signal definition was changed

## Requirements Proved By This UAT

- R002 — Strategy folder structure proven by test case 2 (registry discovers S1 from folder)
- R008 — Strategy registry proven by test cases 1, 2, 3, and the unknown-ID edge case

## Not Proven By This UAT

- R001 — Unified consumption requires S02 (analysis adapter) and S03 (trading adapter) to consume these definitions
- R003 — MarketSnapshot type is defined but not yet produced by real adapters from actual data sources
- R004 — Signal type is defined but not yet consumed by the trading executor or analysis results
- R007 — Identical behavior guarantee requires parity testing in S04
- R005, R006 — Adapter wiring is S02 and S03 respectively

## Notes for Tester

- Use `python3`, not `python` — this system doesn't have a `python` symlink.
- S1's entry_price_threshold is 0.35. Test spike data must produce entry_price ≤ 0.35 or evaluate() correctly returns None. If you modify test prices, verify the resulting entry_price.
- The verify_s01.py script is the most comprehensive single check — run test case 7 first for a quick pass/fail.
