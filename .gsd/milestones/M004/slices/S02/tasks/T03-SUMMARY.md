---
id: T03
parent: S02
milestone: M004
provides:
  - make_trade() function with stop_loss and take_profit parameters that automatically triggers simulator for early exit detection
  - Direction-aware calculate_pnl_exit() that correctly handles Down bet PnL (inverted price semantics)
  - Comprehensive unit test suite (13 tests) covering Up/Down × SL/TP/resolution matrix, NaN handling, edge cases, and PnL correctness
key_files:
  - src/analysis/backtest/engine.py
  - src/tests/test_sl_tp_engine.py
key_decisions:
  - none
patterns_established:
  - SL/TP parameters are keyword-only (backward compatibility pattern)
  - Direction parameter added to calculate_pnl_exit() for correct Down bet PnL (Down bet: entry - exit, Up bet: exit - entry)
  - SL/TP thresholds expressed as Down token values for Down bets, simulator inverts to check against up_price
observability_surfaces:
  - Trade.exit_reason distinguishes 'sl', 'tp', 'resolution' outcomes in all Trade objects
  - Unit tests print descriptive assertion failures showing expected vs actual exit conditions
  - Test fixture creates reproducible synthetic markets for deterministic debugging
duration: 1h
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T03: Integration with make_trade() and comprehensive unit tests

**Integrated SL/TP simulator with make_trade(), fixed Down bet PnL calculation, and wrote 13 comprehensive unit tests covering all exit paths and edge cases.**

## What Happened

Extended `make_trade()` to accept `stop_loss` and `take_profit` keyword-only parameters. When both are provided and a prices array exists in the market dict, the function calls `simulate_sl_tp_exit()` to detect early exits and uses the returned exit_second, exit_price, and exit_reason values to populate the Trade object.

During test implementation, discovered that `calculate_pnl_exit()` was direction-agnostic and incorrectly calculated PnL for Down bets. For Down bets, the PnL formula must be inverted (entry - exit) because Down token semantics are the opposite of Up token semantics. Updated `calculate_pnl_exit()` to accept a `direction` parameter and apply correct formula:
- **Up bets**: PnL = exit_price - entry_price (you bought Yes token)
- **Down bets**: PnL = entry_price - exit_price (you bought No token, which equals 1.0 - up_price)

Wrote 13 unit tests covering:
- **Up bet scenarios**: SL hit, TP hit, no hit (resolution)
- **Down bet scenarios**: SL hit, TP hit, no hit (resolution)
- **Edge cases**: NaN handling, both thresholds hit same second (SL priority), threshold hit at first second after entry, all NaN after entry
- **PnL correctness**: Hand-calculated expected PnL vs actual for SL/TP exits, including direction-specific test for Down bet TP exit

Implemented synthetic market fixture that creates reproducible market dicts with controlled price arrays for deterministic testing.

## Verification

Ran full test suite with 13 tests:
```bash
cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v
```

All tests passed:
- `test_up_bet_sl_hit` - Up bet with price drop below SL → exit_reason='sl', negative PnL
- `test_up_bet_tp_hit` - Up bet with price rise above TP → exit_reason='tp', positive PnL
- `test_up_bet_no_hit` - Up bet with no threshold hit → exit_reason='resolution'
- `test_down_bet_sl_hit` - Down bet with price rise above inverted SL → exit_reason='sl', negative PnL
- `test_down_bet_tp_hit` - Down bet with price drop below inverted TP → exit_reason='tp', positive PnL
- `test_down_bet_no_hit` - Down bet with no threshold hit → exit_reason='resolution'
- `test_nan_handling` - NaN prices skipped, exit at first valid threshold
- `test_both_thresholds_same_second` - SL prioritized when both hit
- `test_exit_at_boundary` - Threshold hit at first second after entry works
- `test_all_nan_after_entry` - All NaN → resolution with last valid price
- `test_pnl_sl_exit` - PnL calculation for SL exit matches hand-calculated
- `test_pnl_tp_exit` - PnL calculation for TP exit matches hand-calculated
- `test_pnl_down_bet_tp_exit` - Down bet PnL calculation correct with direction handling

Verified backward compatibility:
```python
# Without SL/TP - old code path works
trade = make_trade(market, 0, 0.50, 'Up', slippage=0.0, base_rate=0.063)
assert trade.exit_reason == 'resolution'  # ✓

# With SL/TP - simulator path works
trade = make_trade(market, 0, 0.50, 'Up', slippage=0.0, base_rate=0.063, 
                   stop_loss=0.45, take_profit=0.58)
assert trade.exit_reason in ['sl', 'tp', 'resolution']  # ✓
```

Slice verification smoke tests passed (from S02-PLAN.md):
- Up bet with SL hit at correct second
- Up bet with TP hit at correct second
- No-hit case returns 'resolution' with last second and last valid price

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v` | 0 | ✅ pass | 0.31s |
| 2 | Backward compatibility check (make_trade without SL/TP) | 0 | ✅ pass | <0.1s |
| 3 | Slice smoke tests (SL/TP hit verification) | 0 | ✅ pass | <0.1s |

## Diagnostics

**Trade inspection:**
- Every Trade object has `exit_reason` field: 'sl', 'tp', or 'resolution'
- Can filter trades by exit_reason in downstream analysis
- Can compare PnL distributions across exit types

**Test debugging:**
- Test names describe scenario (e.g., `test_down_bet_sl_hit`)
- Assertion messages include expected vs actual values
- Synthetic market fixture creates reproducible price arrays
- Tests fail with clear messages showing wrong exit_reason, exit_second, exit_price, or PnL

**REPL verification pattern:**
```python
from analysis.backtest.engine import make_trade
import numpy as np

market = {
    'market_id': 'test',
    'prices': np.array([0.55, 0.53, 0.48, 0.45, 0.40]),
    'total_seconds': 5,
    'final_outcome': 'Down',
    # ... other fields
}

trade = make_trade(market, 0, 0.55, 'Up', slippage=0.0, base_rate=0.063,
                   stop_loss=0.45, take_profit=0.70)
print(f"Exit: {trade.exit_reason} at second {trade.second_exited}, PnL={trade.pnl}")
```

**Failure modes visible:**
- Wrong exit_reason → test fails with "Expected 'sl', got 'tp'"
- Incorrect exit_second → test fails with "Expected exit at second 3, got 4"
- Wrong PnL calculation → test fails with numerical difference
- Direction handling bug → Down bet tests fail while Up bet tests pass (or vice versa)

## Deviations

**Major deviation:** Added `direction` parameter to `calculate_pnl_exit()` function.

**Reason:** Original task plan assumed `calculate_pnl_exit()` would work correctly for Down bets, but it was direction-agnostic and calculated PnL as `exit - entry` for all trades. For Down bets, this is incorrect because you're buying the No token (1.0 - up_price), so PnL must be inverted: `entry - exit`.

**Impact:** All call sites of `calculate_pnl_exit()` now must pass `direction` parameter. This is a breaking change for any existing code calling this function, but the function was introduced in M003 and only used within `make_trade()` in this codebase, so impact is contained.

**Test count:** Implemented 13 tests instead of the plan's minimum 12. Added `test_pnl_down_bet_tp_exit()` to specifically verify Down bet PnL calculation with the new direction parameter.

## Known Issues

None. All must-haves met, all tests passing, backward compatibility verified.

## Files Created/Modified

- `src/analysis/backtest/engine.py` — Extended `make_trade()` signature with keyword-only `stop_loss` and `take_profit` parameters; added simulator integration logic that calls `simulate_sl_tp_exit()` when both provided; updated `calculate_pnl_exit()` to accept `direction` parameter and correctly handle Down bet PnL (entry - exit for Down, exit - entry for Up)
- `src/tests/test_sl_tp_engine.py` — Implemented synthetic_market fixture; wrote 13 comprehensive tests covering Up/Down × SL/TP/no-hit matrix, NaN handling, edge cases (both thresholds same second, boundary exits, all-NaN scenarios), and PnL correctness verification with hand-calculated expected values
