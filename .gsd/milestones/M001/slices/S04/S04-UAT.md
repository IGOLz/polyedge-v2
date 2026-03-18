# S04: Port S2 + parity verification — UAT

**Milestone:** M001
**Written:** 2026-03-18

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: Strategies are pure functions on numpy arrays — identical input guarantees identical output. No runtime, network, or DB needed. All verification is deterministic script execution.

## Preconditions

- Python 3.x with numpy installed
- Working directory: `src/` within the worktree
- PYTHONPATH includes current directory (`cd src && PYTHONPATH=.`)

## Smoke Test

```bash
cd src && PYTHONPATH=. python3 scripts/parity_test.py
```
Exit 0 with "23 passed, 0 failed" confirms the slice basically works.

## Test Cases

### 1. Registry discovers both S1 and S2

1. Run: `cd src && PYTHONPATH=. python3 -c "from shared.strategies import discover_strategies; r = discover_strategies(); print(sorted(r))"`
2. **Expected:** Output is `['S1', 'S2']`

### 2. S2 fires on volatile data and returns correct signal

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.S2.strategy import S2Strategy
   from shared.strategies.S2.config import get_default_config
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   cfg = get_default_config()
   prices = np.full(60, 0.50)
   prices[20:30] = [0.55, 0.45] * 5  # volatile window
   prices[30] = 0.60  # eval_second price above 0.50
   snap = MarketSnapshot(market_id='test', market_type='test', prices=prices, total_seconds=300, elapsed_seconds=60)
   sig = S2Strategy(cfg).evaluate(snap)
   print(f'direction={sig.direction}, entry_price={sig.entry_price}, strategy={sig.strategy_name}')
   print(f'signal_data keys: {sorted(sig.signal_data.keys())}')
   "
   ```
2. **Expected:** direction=Down (contrarian — price > 0.50), entry_price=0.40, strategy_name=S2_volatility. signal_data contains keys: `['entry_second', 'eval_second', 'price_at_eval', 'spread', 'volatility']`

### 3. S2 returns None on flat data

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.S2.strategy import S2Strategy
   from shared.strategies.S2.config import get_default_config
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   snap = MarketSnapshot(market_id='test', market_type='test', prices=np.full(60, 0.50), total_seconds=300, elapsed_seconds=60)
   result = S2Strategy(get_default_config()).evaluate(snap)
   assert result is None, f'Expected None, got {result}'
   print('S2 correctly returns None on flat data')
   "
   ```
2. **Expected:** Prints "S2 correctly returns None on flat data" — deviation guard (0.08) rejects uniform prices.

### 4. Signal parity — same prices, different elapsed_seconds

1. Run: `cd src && PYTHONPATH=. python3 scripts/parity_test.py`
2. **Expected:** Checks 2-3 (S1 parity, S2 parity) both PASS — signals match exactly when only elapsed_seconds differs. Check 8 (seconds-vs-ticks) confirms 60 prices with elapsed_seconds=45 produces identical signals to elapsed_seconds=60.

### 5. No-signal parity — flat data returns None regardless of context

1. Within parity_test.py output, checks 4 and 5.
2. **Expected:** Both S1 and S2 return None on flat data with both elapsed_seconds=60 and elapsed_seconds=45.

### 6. Multi-strategy auto-test

1. Within parity_test.py output, check 6.
2. **Expected:** Every strategy in `discover_strategies()` evaluated twice with different elapsed_seconds produces matching results. This check auto-covers any new strategy added to the registry.

### 7. Array immutability

1. Within parity_test.py output, check 7.
2. **Expected:** Neither S1 nor S2 mutates the input prices array. Original array equals array after evaluate() call.

### 8. Backtest adapter handles S2 entry_second

1. Run: `cd src && PYTHONPATH=. python3 scripts/verify_s02.py`
2. **Expected:** All 18 checks pass. The adapter's Signal→Trade bridge uses the entry_second→reversion_second→0 fallback chain (D010) — S1 trades still enter at reversion_second, and S2 trades would enter at entry_second.

### 9. S01 regression — no breakage

1. Run: `cd src && PYTHONPATH=. python3 scripts/verify_s01.py`
2. **Expected:** All 17 checks pass. S2 addition and adapter fix didn't break S1 base types, registry, or import isolation.

## Edge Cases

### S2 with insufficient data (< eval_second prices)

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.S2.strategy import S2Strategy
   from shared.strategies.S2.config import get_default_config
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   snap = MarketSnapshot(market_id='test', market_type='test', prices=np.full(20, 0.60), total_seconds=300, elapsed_seconds=20)
   result = S2Strategy(get_default_config()).evaluate(snap)
   assert result is None
   print('Correctly returns None — not enough data for eval_second=30')
   "
   ```
2. **Expected:** Returns None — only 20 prices but eval_second=30 requires at least 31.

### S2 with NaN at eval_second

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.S2.strategy import S2Strategy
   from shared.strategies.S2.config import get_default_config
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   prices = np.full(60, 0.60)
   prices[30] = np.nan
   snap = MarketSnapshot(market_id='test', market_type='test', prices=prices, total_seconds=300, elapsed_seconds=60)
   result = S2Strategy(get_default_config()).evaluate(snap)
   assert result is None
   print('Correctly returns None — NaN at eval_second')
   "
   ```
2. **Expected:** Returns None — NaN guard catches missing price at eval_second.

### S2 with spread outside allowed range

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.S2.strategy import S2Strategy
   from shared.strategies.S2.config import get_default_config
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   prices = np.full(60, 0.98)  # spread = 1.0 - 0.98 = 0.02 < min_spread=0.05
   prices[20:30] = [0.99, 0.97] * 5
   snap = MarketSnapshot(market_id='test', market_type='test', prices=prices, total_seconds=300, elapsed_seconds=60)
   result = S2Strategy(get_default_config()).evaluate(snap)
   assert result is None
   print('Correctly returns None — spread too tight (< 0.05)')
   "
   ```
2. **Expected:** Returns None — spread (0.02) below min_spread (0.05).

## Failure Signals

- `parity_test.py` exits with code 1 — a `[FAIL]` line names the broken invariant
- `verify_s01.py` or `verify_s02.py` exits with code 1 — regression in earlier slices
- `discover_strategies()` doesn't include `S2` — folder structure or __init__.py issue
- S2 `evaluate()` crashes instead of returning None — missing guard

## Requirements Proved By This UAT

- R001 — S1 and S2 each defined once, consumed by both adapters, produce identical signals
- R003 — parity test check 8 proves elapsed_seconds doesn't affect signals — tick-count bug eliminated
- R004 — Single Signal type produced by both S1 and S2, consumed by both adapters
- R007 — 23 parity assertions prove same data → same signals regardless of context
- R008 — Registry auto-discovers S1 and S2 without code changes

## Not Proven By This UAT

- R009, R010 — constraint requirements (no executor/core modifications) not retested here; proven by S03's hash checks
- R011, R012 — deferred to S05 (template + optimization)
- Full adapter pipeline parity — this UAT proves parity at the pure strategy layer, not through the full analysis/trading adapter pipelines

## Notes for Tester

- All test commands assume `cd src && PYTHONPATH=.` — this is required for import resolution.
- S2's guards are ordered and short-circuiting: data length → NaN check → base deviation → spread range → volatility threshold. To debug why S2 didn't fire, check guards in this order.
- The parity test's synthetic data for S1 is calibrated tightly — see KNOWLEDGE.md entry about sharp reversion curves. Don't adjust S1 thresholds without recalibrating the test data.
