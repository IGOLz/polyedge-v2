---
id: T03
parent: S03
milestone: M003
provides:
  - S6 (Streak/Sequence) strategy with intra-market consecutive same-direction window detection
  - Contrarian entry when streak_length consecutive windows move same direction
  - 72-combination parameter grid (4×3×3×2) for window_size, streak_length, min_move_threshold, min_windows
key_files:
  - src/shared/strategies/S6/config.py
  - src/shared/strategies/S6/strategy.py
key_decisions: []
patterns_established:
  - "_get_price() helper with NaN tolerance (consistent S1-S6)"
  - "Entry price clamping to [0.01, 0.99] (consistent S1-S6)"
  - "signal_data['entry_second'] population (consistent S1-S6)"
  - "Windowed analysis pattern: divide market into fixed-size windows, analyze each, aggregate"
observability_surfaces:
  - "Signal.signal_data contains: entry_second, streak_direction, streak_length, window_size"
  - "Strategy returns None for: insufficient windows, flat prices, no valid streak detected"
duration: ~15 minutes
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T03: Implement S6 (Streak/Sequence) simplified intra-market version

**Implemented S6 streak detection strategy with windowed price direction analysis and contrarian entry on consecutive same-direction moves.**

## What Happened

Implemented S6 as a simplified intra-market streak detector that divides the market into fixed-size windows, calculates price direction for each window (up/down/flat based on start-to-end delta vs. `min_move_threshold`), counts consecutive same-direction windows, and enters contrarian when `streak_length` threshold is met.

Key implementation details:
- **Windowed analysis**: Divides `total_seconds` into windows of size `window_size` (default 15s)
- **Direction classification**: For each window, compares start_price to end_price using `_get_price()` helper:
  - `delta > min_move_threshold` → 'up'
  - `delta < -min_move_threshold` → 'down'
  - Otherwise → 'flat'
  - Missing prices → 'unknown'
- **Streak counting**: Scans directions list, increments counter for consecutive same-direction (non-flat) windows, resets on direction change or flat/unknown
- **Contrarian entry**: When `current_streak >= streak_length`, enters opposite direction on next window (rising streak → Down, falling streak → Up)
- **Edge case handling**: Returns None if insufficient windows (`< min_windows`), no room for entry after streak, or entry price unavailable

The strategy is explicitly documented as a simplified intra-market version. True cross-market streak detection (tracking consecutive same-outcome markets across sequential markets) requires state that violates the pure function contract and cannot be implemented within the current architecture.

Parameter grid provides 72 combinations:
- `window_size`: [10, 15, 20, 30]
- `streak_length`: [3, 4, 5]
- `min_move_threshold`: [0.02, 0.03, 0.05]
- `min_windows`: [4, 5]

## Verification

Ran custom verification script covering:
1. **Config structure**: Verified presence of window_size, streak_length, min_move_threshold, min_windows
2. **Parameter grid**: Confirmed 72 combinations (4×3×3×2)
3. **Streak detection**: Synthetic data with 4 consecutive rising windows (linear interpolation within each window) → correctly detected streak and entered Down
4. **Contrarian logic**: Rising streak correctly triggered Down entry (and vice versa)
5. **Edge cases**:
   - Flat prices (no moves) → None
   - Insufficient windows (< min_windows) → None
   - Missing prices → handled via `_get_price()` tolerance
6. **Signal data**: Verified `entry_second`, `streak_length`, `streak_direction`, `window_size` populated
7. **Entry price clamping**: Confirmed [0.01, 0.99] bounds
8. **Docstring**: Verified class docstring documents intra-market limitation and cross-market state constraint

All checks passed on first run after fixing synthetic data pattern (initial test created flat windows with constant prices; revised to linear interpolation within windows).

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd src && PYTHONPATH=. python3 ../verify_t03_must_haves.py` | 0 | ✅ pass | ~0.3s |

## Diagnostics

**Signal inspection**: Each Signal.signal_data contains:
- `entry_second`: Time of contrarian entry (start of window after streak detected)
- `streak_direction`: 'up' or 'down' (direction of detected streak)
- `streak_length`: Number of consecutive same-direction windows (≥ config.streak_length)
- `window_size`: Window size in seconds (from config)

**Parameter grid inspection**: Call `get_param_grid()` from `src/shared/strategies/S6/config.py` to see 72-combination optimization surface.

**Failure modes**: Strategy returns None when:
- `num_windows < min_windows` (insufficient data)
- No streak ≥ `streak_length` detected in directions list
- Streak detected but `entry_second >= total_seconds` (no room for entry)
- Streak detected but `_get_price(entry_second)` returns None (missing price data)
- All windows are flat or unknown (no directional moves)

No crashes on NaN-heavy, flat, or edge-case data.

## Deviations

None — implemented per task plan.

## Known Issues

None — all must-haves verified, strategy ready for backtest integration.

## Files Created/Modified

- `src/shared/strategies/S6/config.py` — Replaced template with real S6Config (window_size, streak_length, min_move_threshold, min_windows) and 72-combination parameter grid
- `src/shared/strategies/S6/strategy.py` — Implemented windowed streak detection with `_get_price()` helper, direction classification, consecutive streak counting, and contrarian entry logic; added limitation note to docstring
