---
id: T02
parent: S04
milestone: M001
provides:
  - Parity test script (scripts/parity_test.py) proving R007 — identical data → identical signals regardless of adapter context
key_files:
  - src/scripts/parity_test.py
key_decisions:
  - Parity proven at pure strategy layer via direct evaluate() calls — no adapter pipeline needed
  - 8 checks cover signal parity, no-signal parity, multi-strategy consistency, array immutability, and seconds-vs-ticks elimination
patterns_established:
  - Parity test uses the same check()/pass/fail pattern as verify_s01.py and verify_s02.py for consistency
observability_surfaces:
  - scripts/parity_test.py prints numbered PASS/FAIL checks and exits 0 (all pass) or 1 (any fail); the last [FAIL] line identifies the broken invariant
duration: 6m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T02: Build parity test script proving identical signals across adapters

**Created parity_test.py with 23 checks proving S1 and S2 produce identical signals on identical price data regardless of elapsed_seconds — seconds-vs-ticks bug eliminated by construction**

## What Happened

Created `src/scripts/parity_test.py` with 8 numbered check groups (23 individual assertions):

1. **Registry discovery** — confirms both S1 and S2 are auto-discovered
2. **S1 signal parity** — spike+reversion data produces identical Signal (direction, entry_price, strategy_name) with elapsed_seconds=60 vs elapsed_seconds=45
3. **S2 signal parity** — volatility data produces identical Signal with different elapsed_seconds, including matching signal_data['volatility']
4. **S1 no-signal parity** — flat data returns None regardless of elapsed_seconds
5. **S2 no-signal parity** — flat data returns None regardless of elapsed_seconds
6. **Multi-strategy consistency** — every discovered strategy evaluated twice with different elapsed_seconds produces matching results
7. **Array immutability** — neither strategy mutates the prices array
8. **Seconds-vs-ticks bug elimination** — 60 price points with elapsed_seconds=45 still fires correctly, producing identical signals to elapsed_seconds=60

The script imports only from `shared.strategies` — no trading or analysis imports. This proves parity at the pure strategy layer.

## Verification

- `parity_test.py`: 23/23 checks pass, exit 0
- `verify_s01.py`: 17/17 checks pass (no regressions)
- `verify_s02.py`: 18/18 checks pass (no regressions)
- Registry discovers both S1 and S2
- S2 returns None on flat data (failure-path diagnostic)
- No forbidden imports in parity_test.py (only shared.strategies)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `scripts/parity_test.py` (23 checks) | 0 | ✅ pass | 5.8s |
| 2 | `scripts/verify_s01.py` (17 checks) | 0 | ✅ pass | 5.8s |
| 3 | `scripts/verify_s02.py` (18 checks) | 0 | ✅ pass | 5.8s |
| 4 | `discover_strategies()` asserts S1+S2 | 0 | ✅ pass | 3.1s |
| 5 | S2 returns None on flat data | 0 | ✅ pass | 3.1s |

## Diagnostics

- **Run parity test:** `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — prints per-check verdicts, exits 0 on success
- **Debug a failing check:** The `[FAIL]` line names the exact invariant that broke. Check the corresponding synthetic data builder (`_make_s1_triggering_prices`, `_make_s2_triggering_prices`) and strategy config thresholds.
- **Add new strategies:** Check 6 (multi-strategy consistency) automatically tests any strategy discovered by the registry — no code changes needed when S3+ are added.

## Deviations

None — implementation matched the plan exactly.

## Known Issues

None.

## Files Created/Modified

- `src/scripts/parity_test.py` — parity test script with 8 check groups (23 assertions) proving signal identity across adapter contexts
- `.gsd/milestones/M001/slices/S04/tasks/T02-PLAN.md` — added Observability Impact section (pre-flight fix)
