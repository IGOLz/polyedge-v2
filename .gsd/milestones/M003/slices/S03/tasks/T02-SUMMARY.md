---
id: T02
parent: S03
milestone: M003
provides:
  - S4 (Volatility Regime) strategy with rolling std dev calculation and contrarian entry on high vol + extreme price
  - S5 (Time-Phase Entry) strategy with time-window filtering and optional hour-of-day constraints
key_files:
  - src/shared/strategies/S4/config.py
  - src/shared/strategies/S4/strategy.py
  - src/shared/strategies/S5/config.py
  - src/shared/strategies/S5/strategy.py
key_decisions: []
patterns_established:
  - _get_price(prices, target_sec, tolerance) helper for NaN-aware price lookup (consistent across S1-S5)
  - Entry price clamping to [0.01, 0.99] before returning signals (consistent pattern)
  - Volatility calculation requiring minimum 10 valid prices (statistical validity threshold)
  - Hour-of-day filtering with None as "all hours allowed" (optional constraint pattern)
observability_surfaces:
  - Signal.signal_data['volatility'] for S4 (shows std dev calculation)
  - Signal.signal_data['hour'] for S5 (shows hour filter result)
  - Signal.signal_data['entry_second'] for both (canonical entry timing)
duration: 31m
verification_result: passed
completed_at: 2026-03-18 13:58
blocker_discovered: false
---

# T02: Implement S4 (Volatility Regime), S5 (Time-Phase Entry)

**Implemented S4 volatility regime strategy with rolling std dev detection and S5 time-phase entry strategy with hour-of-day filtering, both with 108-combination parameter grids and robust NaN handling.**

## What Happened

Implemented two standalone strategies that build on the framework established in T01:

**S4 (Volatility Regime):** Calculates rolling standard deviation over a lookback window (30/60/90s) at a specific evaluation point (60/120/180s). Enters contrarian when volatility ≥ threshold (0.05/0.08/0.10) AND current price is extreme (≤0.25-0.30 → bet Up, ≥0.70-0.75 → bet Down). Logic: high volatility + extreme price suggests overreaction → fade it. Requires minimum 10 valid prices in lookback window for statistical validity (returns None if insufficient data). Handles flat prices gracefully (std_dev = 0 → no volatility → no signal).

**S5 (Time-Phase Entry):** Scans entry window (start: 30/60/90s, end: 120/180/240s) for price in target range (0.40-0.45 to 0.55-0.60). Optional hour-of-day filter (None = all hours, or specific hour lists like [10-15] or [14-18]). Direction: if price < 0.50, bet Up (toward middle); if price > 0.50, bet Down. Handles empty allowed_hours list (no hours allowed → no signal), clamps window_end to available data, skips exact 0.50 price (no clear direction).

Both strategies use the `_get_price()` helper pattern from T01 for NaN-tolerant price lookup with ±5s scanning, clamp entry_price to [0.01, 0.99], and populate signal_data['entry_second'] for diagnostic visibility.

## Verification

**Task plan verification script:** Ran synthetic evaluation tests on both strategies:
- S4 with high volatility pattern (swinging 0.30 ↔ 0.70): generated Up signal when current price extreme low
- S5 with price=0.52 at second 90: generated Down signal (price > 0.50, bet toward middle)
- Both strategies handled sparse NaN data without crashes
- Both parameter grids verified to have 108 combinations (3×3×3×2×2)

**Detailed spot-checks:**
- S4: high vol + extreme low → Up, high vol + extreme high → Down, low vol → no signal, <10 valid prices → no signal
- S5: price 0.52 → Down, price 0.48 → Up, hour filter blocks wrong hour, hour filter allows correct hour, window clamping works

**Must-haves verification:**
- All config fields present (lookback_window, vol_threshold, eval_second, extreme_price_low/high for S4; entry_window_start/end, allowed_hours, price_range_low/high for S5)
- Both use `_get_price` helper
- Both calculate correct signals and clamp entry_price to [0.01, 0.99]
- Both populate entry_second in signal_data
- Both return None for insufficient/invalid data

Exit code 0 on all verification scripts.

## Verification Evidence

No automated verification gate ran (slice verification script `scripts/verify_s03_strategies.sh` deferred to final task of slice). Manual verification scripts executed successfully:

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd src && PYTHONPATH=. python3 ../test_s4_s5.py` | 0 | ✅ pass | ~1s |
| 2 | `cd src && PYTHONPATH=. python3 ../test_s4_s5_detailed.py` | 0 | ✅ pass | ~1s |
| 3 | `cd src && PYTHONPATH=. python3 ../verify_t02_must_haves.py` | 0 | ✅ pass | ~1s |

## Diagnostics

**Signal inspection:** Each Signal.signal_data contains strategy-specific metrics:
- S4: `volatility` (std dev), `current_price`, `entry_second`
- S5: `price`, `hour`, `entry_second`

**Parameter grid inspection:** Call `get_param_grid()` from each config module to see optimization surface:
- S4: 3 lookback windows × 3 vol thresholds × 3 eval times × 2 extreme lows × 2 extreme highs = 108
- S5: 3 window starts × 3 window ends × 3 hour filters × 2 price lows × 2 price highs = 108

**Failure modes:**
- S4 returns None when: elapsed_seconds < eval_second, lookback window extends before time 0, < 10 valid prices in window, volatility < threshold, price not extreme
- S5 returns None when: hour filter specified and current hour not in allowed_hours, no price in target range within entry window, price exactly 0.50 (no clear direction)

No crashes on NaN-heavy, flat, or edge-case data.

## Deviations

None — implemented according to task plan specification.

## Known Issues

None — all must-haves met, all verification passed.

## Files Created/Modified

- `src/shared/strategies/S4/config.py` — S4 config with lookback_window, vol_threshold, eval_second, extreme_price_low/high parameters and 108-combination param grid
- `src/shared/strategies/S4/strategy.py` — S4 evaluate() with rolling std dev calculation, contrarian entry on high vol + extreme price, _get_price helper, entry_price clamping
- `src/shared/strategies/S5/config.py` — S5 config with entry_window_start/end, allowed_hours, price_range_low/high parameters and 108-combination param grid
- `src/shared/strategies/S5/strategy.py` — S5 evaluate() with time-window scanning, hour-of-day filtering, bet-toward-middle direction logic, _get_price helper, entry_price clamping
