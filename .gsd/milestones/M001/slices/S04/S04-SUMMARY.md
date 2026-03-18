---
id: S04
parent: M001
milestone: M001
provides:
  - S2 volatility strategy (shared/strategies/S2/) — pure, synchronous, numpy-only
  - Generic entry_second fallback chain in backtest adapter Signal→Trade bridge (D010)
  - Parity test script (scripts/parity_test.py) proving identical signals across adapter contexts (R007)
  - Proof that seconds-vs-ticks bug is eliminated by construction (R003)
requires:
  - slice: S02
    provides: analysis/backtest_strategies.py adapter with Signal→Trade bridge
  - slice: S03
    provides: trading/strategy_adapter.py with ticks_to_snapshot conversion
affects:
  - S05
key_files:
  - src/shared/strategies/S2/__init__.py
  - src/shared/strategies/S2/config.py
  - src/shared/strategies/S2/strategy.py
  - src/analysis/backtest_strategies.py
  - src/scripts/parity_test.py
key_decisions:
  - D009: Parity proven at pure strategy layer via direct evaluate() calls — no adapter pipeline needed
  - D010: entry_second → reversion_second → 0 fallback chain replaces hardcoded reversion_second in Signal→Trade bridge
  - S2 uses np.nanstd() with ddof=0 (population std), matching both M4 trading implementation and analysis backtest convention
patterns_established:
  - S2 follows the exact S1 directory/class pattern (config.py, strategy.py, __init__.py) — validates the pattern is repeatable
  - Parity test uses same check()/PASS/FAIL pattern as verify_s01.py and verify_s02.py
  - Multi-strategy consistency check auto-tests any newly registered strategy without code changes
observability_surfaces:
  - scripts/parity_test.py prints numbered PASS/FAIL checks (23 assertions) and exits 0/1
  - S2 Signal.signal_data includes eval_second, spread, volatility, entry_second, price_at_eval
  - discover_strategies() returns dict of all registered strategy IDs
drill_down_paths:
  - .gsd/milestones/M001/slices/S04/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S04/tasks/T02-SUMMARY.md
duration: 14m
verification_result: passed
completed_at: 2026-03-18
---

# S04: Port S2 + parity verification

**S2 volatility strategy ported and parity test script proves identical signals on identical data — seconds-vs-ticks bug provably eliminated**

## What Happened

Two tasks delivered S04's goal of proving the unified strategy framework is correct and complete across multiple strategies.

**T01** created the S2 volatility strategy in `shared/strategies/S2/`, porting the M4 detection logic from `trading/strategies.py::evaluate_m4_signal()`. All async, DB, balance, and timing guards were stripped — the result is a pure, synchronous function operating on `MarketSnapshot.prices` numpy array. S2Config matches M4_CONFIG exactly (eval_second=30, eval_window=2, volatility_window_seconds=10, volatility_threshold=0.05, min_spread=0.05, max_spread=0.50, base_deviation=0.08). The strategy uses np.nanstd with ddof=0 for population std, matching the original implementation. T01 also fixed the backtest adapter's Signal→Trade bridge: the hardcoded `reversion_second` extraction became a generic `entry_second → reversion_second → 0` fallback chain (D010), making the bridge strategy-agnostic.

**T02** created `scripts/parity_test.py` with 8 check groups (23 individual assertions) that prove R007 — identical MarketSnapshot data produces identical signals regardless of context. The key insight: strategies are pure functions on prices arrays, so varying `elapsed_seconds` while keeping prices constant proves signals depend only on the data, not on which adapter built the snapshot. The test covers: registry discovery (both S1 and S2), signal parity (both strategies fire identically with different elapsed_seconds), no-signal parity (both return None on flat data), multi-strategy consistency (auto-tests all registered strategies), array immutability (strategies don't mutate input), and seconds-vs-ticks elimination (60 prices with elapsed_seconds=45 fires identically to elapsed_seconds=60).

## Verification

All 5 slice-level verification commands pass:

| # | Check | Result |
|---|-------|--------|
| 1 | `scripts/parity_test.py` — 23/23 assertions | ✅ pass |
| 2 | `discover_strategies()` returns S1 and S2 | ✅ pass |
| 3 | `scripts/verify_s01.py` — 17/17 checks (S01 regression) | ✅ pass |
| 4 | `scripts/verify_s02.py` — 18/18 checks (S02 regression) | ✅ pass |
| 5 | S2 returns None on flat data (failure-path diagnostic) | ✅ pass |

## Requirements Advanced

- R009 — S04 made zero modifications to executor, redeemer, balance, or DB tables. The only change was the entry_second fallback in the adapter bridge.
- R010 — `src/core/` untouched throughout S04.

## Requirements Validated

- R001 — S1 and S2 each defined once in shared/strategies/ and consumed by both adapters. parity_test.py proves identical signals (23/23 checks).
- R003 — parity_test.py check 8 proves strategies operate on array indices not elapsed_seconds. The tick-count-as-time bug is eliminated by construction.
- R004 — Signal dataclass from shared/strategies/base.py used by both adapters. S1 and S2 both produce Signal objects with identical fields.
- R007 — parity_test.py: 23 assertions prove same config + same data → identical signals regardless of adapter context.
- R008 — discover_strategies() auto-discovers S1 and S2 via folder scanning. Adding S2 required zero registry changes.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

None — both T01 and T02 implemented exactly as planned.

## Known Limitations

- Parity is proven at the pure strategy layer (evaluate() calls), not through the full adapter pipelines. This is by design (D009) — strategies are pure functions, so adapter-level testing adds no value for signal parity.
- S2's silent None returns on guard failures require manual MarketSnapshot construction to diagnose why a specific market didn't trigger.

## Follow-ups

- none — S05 (strategy template + parameter optimization) is the planned next slice.

## Files Created/Modified

- `src/shared/strategies/S2/__init__.py` — empty init for auto-discovery
- `src/shared/strategies/S2/config.py` — S2Config dataclass with M4 parameters + get_default_config()
- `src/shared/strategies/S2/strategy.py` — S2Strategy with pure volatility detection evaluate()
- `src/analysis/backtest_strategies.py` — entry_second→reversion_second→0 fallback chain (1-line fix)
- `src/scripts/parity_test.py` — 8 check groups, 23 assertions proving signal parity

## Forward Intelligence

### What the next slice should know
- The strategy directory pattern is now proven across two strategies (S1, S2). TEMPLATE should follow the exact same structure: `__init__.py` (empty), `config.py` (dataclass + get_default_config), `strategy.py` (BaseStrategy subclass with evaluate).
- Check 6 in parity_test.py auto-tests any strategy in the registry — adding a new strategy folder automatically gets parity coverage without test changes.
- The backtest adapter's entry_second fallback chain (D010) handles any strategy that puts `entry_second` or `reversion_second` in signal_data. New strategies should use `entry_second` as the canonical key.

### What's fragile
- S1 synthetic data calibration is sensitive to threshold alignment — see KNOWLEDGE.md entry about sharp reversion curves. If S1 thresholds change, parity_test.py's synthetic data builders may need recalibration.
- S2's `base_deviation=0.08` guard means test data must have the eval_second price deviate enough from 0.50 — the alternating 0.55/0.45 pattern in parity_test.py barely clears this.

### Authoritative diagnostics
- `scripts/parity_test.py` exit code 0 — definitive proof that the framework delivers R007. If this breaks, the framework is wrong.
- `scripts/verify_s01.py` and `scripts/verify_s02.py` — regression gates for S01 and S02 respectively. Run all three scripts for full confidence.

### What assumptions changed
- No assumptions changed. The plan predicted strategies are pure functions and parity would be trivial to prove — this was correct.
