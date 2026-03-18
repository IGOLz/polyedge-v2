---
id: T01
parent: S03
milestone: M003
provides:
  - S1 Calibration strategy with real detection logic (deviation from 0.50)
  - S2 Momentum strategy with velocity-based contrarian entry
  - S3 Mean Reversion strategy with spike → reversion detection
  - _get_price() helper for NaN-aware price lookup across all three strategies
  - Parameter grids with 72-144 combinations per strategy
key_files:
  - src/shared/strategies/S1/config.py
  - src/shared/strategies/S1/strategy.py
  - src/shared/strategies/S2/config.py
  - src/shared/strategies/S2/strategy.py
  - src/shared/strategies/S3/config.py
  - src/shared/strategies/S3/strategy.py
key_decisions: []
patterns_established:
  - _get_price(prices, target_sec, tolerance) helper for NaN-tolerant price lookup with ±tolerance scanning
  - Entry price clamping to [0.01, 0.99] before returning signals
  - signal_data['entry_second'] as canonical entry timestamp field
  - Contrarian entry logic (S1: bet against mispricing, S2: fade momentum, S3: fade spike after reversion)
observability_surfaces:
  - Signal.signal_data contains strategy-specific detection metrics (deviation, velocity, spike_direction)
  - Parameter grids expose optimization surface via get_param_grid()
duration: 8 minutes
verification_result: passed
completed_at: 2026-03-18T13:58:36+01:00
blocker_discovered: false
---

# T01: Implement S1 (Calibration), S2 (Momentum), S3 (Mean Reversion)

**Implemented three foundational strategies with real signal detection logic: S1 detects calibration mispricing (deviation from 0.50), S2 detects early momentum (velocity between 30-60s), S3 detects mean reversion (spike → reversion pattern), all with parameter grids of 72-144 combinations.**

## What Happened

Ported detection logic from reference implementations into the shared strategy framework:

1. **S1 Calibration Mispricing**: Scans 30-60s window for price deviation from 0.50. Enters Up if price < 0.45 with deviation ≥ 0.08, Down if price > 0.55. Parameter grid: 3×3×2×2×3 = 108 combinations.

2. **S2 Early Momentum**: Calculates velocity between eval_window_start (30s) and eval_window_end (60s). Enters Down (contrarian) if velocity ≥ 0.03 (rising), Up if velocity ≤ -0.03 (falling). Parameter grid: 3×3×4×2 = 72 combinations.

3. **S3 Mean Reversion**: Two-phase detection:
   - Phase 1: Scan first spike_lookback (30s) for price spike (UP ≥ 0.75 or DOWN ≥ 0.75)
   - Phase 2: Wait for reversion (price moves back ≥ 10% from peak within min_reversion_sec)
   - Enter contrarian: Down for Up spike, Up for Down spike
   - Parameter grid: 4×3×4×3 = 144 combinations

Added `_get_price(prices, target_sec, tolerance=5)` helper to all three strategies for NaN-aware price lookup — scans ±tolerance seconds if target is NaN. All strategies clamp entry_price to [0.01, 0.99] and populate signal_data['entry_second'].

## Verification

Ran comprehensive verification covering:

1. **Import and instantiation**: All three strategies import without errors and instantiate with default config
2. **Parameter grids**: All grids have ≥2 parameters with ≥2 values each, totaling 72-144 combinations
3. **Signal detection**:
   - S1: Detects low price (0.42) → bets Up with correct deviation
   - S2: Detects strong momentum (0.05→0.99 over 30s) → bets Down (contrarian) with velocity 0.0313
   - S3: Detects spike (0.85) + reversion → bets Down with spike_direction='Up'
4. **Entry price clamping**: All signals have entry_price in [0.01, 0.99]
5. **signal_data fields**: All signals contain 'entry_second'
6. **Graceful degradation**: All strategies return None on insufficient data (no crashes)
7. **Pattern variety**: Tested with spike, flat, NaN-heavy, low/high price, momentum up/down patterns

All verification passed.

## Verification Evidence

No automated verification gate ran (slice verification script `scripts/verify_s03_strategies.sh` not yet created — expected in later task). Manual verification script executed all checks successfully.

## Diagnostics

**Signal inspection**: Each Signal.signal_data contains strategy-specific metrics:
- S1: `deviation`, `price`
- S2: `velocity`, `price_30s`, `price_60s`
- S3: `spike_direction`, `peak_second`, `peak_price`, `reversion_amount`

**Parameter grid inspection**: Call `get_param_grid()` from each config module to see optimization surface.

**Failure mode**: Strategies return `None` when:
- Insufficient data (len(prices) < required window)
- All prices NaN in required window
- Detection thresholds not met
- No valid entry opportunity found

No crashes on NaN-heavy or edge-case data.

## Deviations

None — implemented exactly as specified in task plan.

## Known Issues

None. All must-haves verified, strategies handle edge cases gracefully, parameter grids are well-sized for optimization.

## Files Created/Modified

- `src/shared/strategies/S1/config.py` — Added real config fields (entry windows, price thresholds, min_deviation) and parameter grid with 108 combinations
- `src/shared/strategies/S1/strategy.py` — Added _get_price() helper and implemented calibration mispricing detection logic
- `src/shared/strategies/S2/config.py` — Added momentum config fields (eval windows, threshold, tolerance) and parameter grid with 72 combinations
- `src/shared/strategies/S2/strategy.py` — Added _get_price() helper and implemented velocity-based momentum detection logic
- `src/shared/strategies/S3/config.py` — Added mean reversion config fields (spike threshold, lookback, reversion %, min seconds) and parameter grid with 144 combinations
- `src/shared/strategies/S3/strategy.py` — Added _get_price() helper and implemented two-phase spike → reversion detection logic
