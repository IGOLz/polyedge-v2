---
id: T02
parent: S02
milestone: M004
provides:
  - simulate_sl_tp_exit() function that scans price arrays and detects SL/TP threshold hits
  - Direction-specific threshold logic (Up vs Down bet handling with inverted thresholds)
  - NaN price handling with last_valid_price fallback
  - Resolution fallback when no threshold hit
key_files:
  - src/analysis/backtest/engine.py
key_decisions:
  - none
patterns_established:
  - Pure function pattern for simulation - no side effects, deterministic, testable in isolation
  - SL priority over TP when both hit same second (risk management first)
  - Last valid price tracking for resolution fallback when final price is NaN
observability_surfaces:
  - Function returns (exit_second, exit_price, exit_reason) tuple - all values directly inspectable
  - exit_reason string with three semantic values: 'sl', 'tp', 'resolution'
  - exit_second indicates exact timing of threshold hit (or market close)
  - exit_price is actual market price at exit (not threshold value)
duration: 25m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T02: Implement simulate_sl_tp_exit() core function

**Implemented price-scanning engine that detects stop loss and take profit threshold hits with direction-specific logic and NaN handling**

## What Happened

Added `simulate_sl_tp_exit()` function to `engine.py` between helper functions and `make_trade()`. The function implements the threshold detection logic documented in decision D012:

- **Up bets**: SL when price ≤ stop_loss, TP when price ≥ take_profit
- **Down bets**: Inverts thresholds because Down token price = 1.0 - up_price
  - SL when price ≥ (1.0 - stop_loss)
  - TP when price ≤ (1.0 - take_profit)

Function scans the prices array from entry_second + 1 onward, skips NaN prices, and returns as soon as a threshold is hit. If both SL and TP hit in the same second (impossible in practice but code is defensive), SL is prioritized for risk management. If no threshold hits before array end, returns 'resolution' with the last valid price found during scan.

Implementation is ~65 lines including comprehensive docstring. All smoke tests and edge cases pass.

## Verification

Ran manual smoke tests as specified in task plan verification section:

1. **Up bet SL hit**: Price array drops to 0.45 → exits at second 3 with reason 'sl' ✓
2. **Up bet TP hit**: Price array rises to 0.72 → exits at second 4 with reason 'tp' ✓  
3. **Down bet SL hit**: Price rises above inverted threshold → exits with reason 'sl' ✓

Additional edge case verification:

4. **NaN handling**: Array with NaN gaps → skips invalid seconds, exits at first valid threshold hit ✓
5. **Resolution fallback**: No threshold hit → returns 'resolution' at last second ✓
6. **Down bet TP hit**: Price drops below inverted threshold → exits with reason 'tp' ✓
7. **All NaN after entry**: Uses entry_price as last_valid_price fallback ✓
8. **Mid-array entry**: Entry at second > 0 → scans correctly from entry onward ✓

Observability signals verified:

- Return values are correct types (int, float, str)
- exit_reason always in ['sl', 'tp', 'resolution']
- exit_second shows exact timing including NaN gap behavior
- exit_price is actual market price (not threshold)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | Smoke tests (Up SL, Up TP, Down SL) | 0 | ✅ pass | <1s |
| 2 | Edge cases (NaN, resolution, Down TP, mid-entry) | 0 | ✅ pass | <1s |
| 3 | Slice smoke tests (exact format from slice plan) | 0 | ✅ pass | <1s |
| 4 | Resolution fallback diagnostic | 0 | ✅ pass | <1s |
| 5 | Observability signals verification | 0 | ✅ pass | <1s |
| 6 | Function signature and docstring check | 0 | ✅ pass | <1s |

## Diagnostics

**Inspection surfaces:**

- Function is pure and deterministic — same inputs always produce same outputs
- No internal state, no side effects, no logging
- Can be tested in isolation with synthetic numpy arrays (T03 will add comprehensive unit tests)
- Return tuple directly unpacks: `exit_sec, exit_price, reason = simulate_sl_tp_exit(...)`

**REPL verification pattern:**

```python
import numpy as np
from analysis.backtest.engine import simulate_sl_tp_exit

prices = np.array([0.55, 0.53, 0.48, 0.45, 0.40, 0.38])
exit_sec, exit_price, reason = simulate_sl_tp_exit(
    prices, entry_second=0, entry_price=0.55,
    direction='Up', stop_loss=0.45, take_profit=0.70
)
print(f"Exit at second {exit_sec}: price={exit_price}, reason='{reason}'")
```

**Failure modes visible:**

- Wrong direction handling → systematic pattern of incorrect exits for all Up or Down bets
- Off-by-one error → exit_second consistently wrong by 1
- NaN handling bug → function crashes with NaN comparison error (Python raises exception)
- Missing resolution fallback → function crashes with no return statement (Python raises error)

**Performance:**

- O(n) scan where n = seconds in market (typically 300)
- Each second: 2-4 float comparisons + 1 NaN check
- No allocations, no copies of price array
- Fast enough for grid search with thousands of markets × thousands of parameter combinations

## Deviations

none

## Known Issues

none

## Files Created/Modified

- `src/analysis/backtest/engine.py` — Added `simulate_sl_tp_exit()` function (~65 lines) that scans price arrays for SL/TP threshold hits with direction-specific logic, NaN handling, and resolution fallback
