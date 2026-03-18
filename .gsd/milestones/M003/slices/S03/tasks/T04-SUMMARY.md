---
id: T04
parent: S03
milestone: M003
provides:
  - S7 (Composite Ensemble) strategy with inline multi-pattern detection and voting logic
  - Three inline detection methods (_detect_calibration, _detect_momentum, _detect_volatility) duplicating core logic from S1, S2, S4
  - Voting mechanism that returns signal only when ≥ min_agreement patterns agree on direction
  - Parameter grid with 192 combinations exploring ensemble configurations
key_files:
  - src/shared/strategies/S7/config.py
  - src/shared/strategies/S7/strategy.py
key_decisions:
  - D011 referenced (inline pattern duplication to maintain pure function contract)
patterns_established:
  - "Inline pattern detection: Composite strategy duplicates logic from S1/S2/S4 inline rather than calling those strategies (pure function contract prevents registry access)"
  - "Voting mechanism: Collect (direction, confidence) tuples from all enabled patterns, count votes by direction, return signal only if ≥ min_agreement threshold met"
  - "Entry price from representative window: Use momentum_eval_end (60s) as canonical entry_second when multiple patterns agree"
observability_surfaces:
  - Signal.signal_data contains voting breakdown (up_votes, down_votes, detections count) for understanding why ensemble entered
duration: 25m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T04: Implement S7 (Composite Ensemble) with inline multi-pattern detection

**Implemented S7 composite ensemble strategy with inline duplication of calibration, momentum, and volatility detection patterns plus voting logic that returns signals only when ≥ min_agreement patterns agree on direction.**

## What Happened

Implemented the S7 composite ensemble strategy, the most architecturally complex strategy in the set. The pure function contract for `evaluate()` prevents accessing the registry or calling other strategies, so the solution duplicates core detection logic from S1 (calibration), S2 (momentum), and S4 (volatility) inline.

Implementation steps:
1. **Config parameters:** Added ensemble configuration (min_agreement, per-pattern enable flags) plus threshold parameters for each inline detection pattern (calibration_deviation, momentum_threshold, volatility_threshold, extreme price thresholds)

2. **Parameter grid:** Configured 192-combination grid exploring ensemble configurations (which patterns enabled, agreement thresholds, detection thresholds)

3. **Inline detection methods:** Implemented three private methods that duplicate simplified versions of S1/S2/S4 logic:
   - `_detect_calibration()`: Scans early window for price deviation from 0.50, returns ('Up'|'Down', confidence) or None
   - `_detect_momentum()`: Calculates velocity between 30s-60s, returns contrarian signal or None
   - `_detect_volatility()`: Calculates rolling std dev, checks for high vol + extreme price, returns contrarian signal or None

4. **Voting logic in evaluate():** Runs all enabled patterns, collects (direction, confidence) tuples, counts votes by direction, returns Signal only if up_votes >= min_agreement OR down_votes >= min_agreement

5. **Entry price calculation:** Uses momentum_eval_end (60s) as representative entry_second, applies direction adjustment and clamping to [0.01, 0.99]

6. **Documentation:** Added comprehensive docstring documenting inline duplication limitation and manual sync requirement if S1/S2/S4 change

The strategy correctly handles edge cases:
- Only 1 pattern triggers (returns None when min_agreement=2)
- Patterns disagree (1 says Up, 1 says Down → returns None)
- Multiple patterns agree (2+ same direction → returns Signal)

## Verification

Ran comprehensive checks:
1. Config verification: Confirmed all required fields present (min_agreement, enable flags, thresholds for each pattern)
2. Param grid verification: Confirmed 192 combinations generated from 7 parameters
3. Method verification: Confirmed all three detection methods (_detect_calibration, _detect_momentum, _detect_volatility) exist
4. Signal verification: Tested on synthetic data with 2+ agreeing patterns, confirmed signal generated with correct direction
5. Entry price verification: Confirmed clamping to [0.01, 0.99]
6. signal_data verification: Confirmed voting details present (entry_second, up_votes, down_votes, detections)
7. Edge case verification: Confirmed returns None when min_agreement not met (only 1 pattern triggers)
8. Registry integration: Confirmed S7 discovered by strategy registry

All checks passed. The composite ensemble correctly implements voting logic and returns signals only when consensus is reached.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | Manual verification script (inline Python checks) | 0 | ✅ pass | <1s |
| 2 | Registry integration check | 0 | ✅ pass | <1s |

## Diagnostics

**Signal inspection:** Each Signal.signal_data contains:
- `entry_second`: Time of entry (60s, from momentum window)
- `up_votes`: Number of patterns that voted Up
- `down_votes`: Number of patterns that voted Down
- `detections`: Total number of patterns that triggered (up_votes + down_votes)

**Parameter grid inspection:** Call `get_param_grid()` from `src/shared/strategies/S7/config.py` to see 192-combination optimization surface.

**Failure modes:** Strategy returns None when:
- Fewer than min_agreement patterns agree on same direction
- No patterns trigger (all return None due to insufficient data or thresholds not met)
- Patterns disagree (some vote Up, some vote Down, neither reaches min_agreement)
- Entry price lookup fails (returns None at entry_second)

**Inline duplication impact:** If S1/S2/S4 detection logic changes, S7 must be updated manually. The inline detection methods are simplified versions that may diverge from their source strategies over time.

No crashes on NaN-heavy, flat, or edge-case data.

## Deviations

None — implemented exactly as specified in task plan.

## Known Issues

None. The inline duplication is documented and accepted as a constraint of the pure function contract. Future refactoring could extract shared detection functions into a utility module (noted in forward intelligence).

## Files Created/Modified

- `src/shared/strategies/S7/config.py` — Replaced template fields with ensemble configuration (min_agreement, enable flags, per-pattern thresholds); added 192-combination parameter grid
- `src/shared/strategies/S7/strategy.py` — Implemented S7Strategy with three inline detection methods (_detect_calibration, _detect_momentum, _detect_volatility) and voting logic in evaluate(); added comprehensive docstring documenting inline duplication limitation and manual sync requirement
