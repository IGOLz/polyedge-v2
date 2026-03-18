---
id: T02
parent: S03
milestone: M001
provides:
  - trading/main.py import rewired to use shared strategy adapter
  - scripts/verify_s03.py — 18-check contract verification for S03 pipeline (import chain, conversion, signal fields, guards, integrity, isolation)
key_files:
  - src/trading/main.py
  - src/scripts/verify_s03.py
key_decisions: []
patterns_established:
  - Verification script mocks py_clob_client/trading.config/shared.db/colorama before any trading imports — same pattern as T01 import tests
observability_surfaces:
  - "`cd src && PYTHONPATH=. python3 scripts/verify_s03.py` — exit code 0/1, 18 checks covering full S03 pipeline"
  - "R009 integrity checks (16-17) will fail visibly if executor.py, redeemer.py, or balance.py are ever modified"
duration: 8m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T02: Rewire main.py import + build verification script

**Rewired `trading/main.py` to import `evaluate_strategies` from `trading.strategy_adapter` and built 18-check verification script proving full adapter pipeline — tick conversion, strategy evaluation, executor-compatible signals, and R009 file integrity**

## What Happened

Two deliverables:

1. **Import rewire (1 line):** Changed `from trading.strategies import evaluate_strategies` → `from trading.strategy_adapter import evaluate_strategies` in `trading/main.py` line 20. This is the only modification to main.py — all other imports and logic remain unchanged.

2. **Verification script (`scripts/verify_s03.py`, 18 checks):** Built following the established pattern from verify_s01.py/verify_s02.py. Mocks external dependencies (py_clob_client, trading.config, shared.db, colorama) before importing trading modules, then exercises:
   - Import chain resolution (checks 1-3)
   - Tick-to-snapshot conversion with gap handling (checks 4-7) — synthetic MarketInfo + Tick objects, verifies NaN for missing seconds and correct values at known seconds
   - S1 strategy evaluation on calibrated spike-reversion data (checks 8-10) — spike peak at s=4 to 0.85, reversion to 0.75 by s=11
   - `_populate_execution_fields` producing all executor-required fields (checks 11-14) — locked_shares, locked_cost, price_min/max, profitability_thesis
   - Empty ticks guard (check 15) — produces all-NaN array without crash
   - R009 file hash integrity (checks 16-17) — executor.py, redeemer.py, balance.py match originals in main repo
   - Module isolation (check 18) — no analysis.* or core.* imports in adapter (AST parse)

## Verification

All 18 checks pass with exit code 0:
- `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` → 18 passed, 0 failed
- `grep "from trading.strategy_adapter import evaluate_strategies" src/trading/main.py` → 1 match
- `grep "from trading.strategies import evaluate_strategies" src/trading/main.py` → 0 matches

### Slice-level verification status (S03 — final task)

All 12 slice verification items are covered by verify_s03.py checks:
1. ✅ Import chain resolves (checks 1-2)
2. ✅ ticks_to_snapshot produces correct numpy array (checks 4-7)
3. ✅ elapsed_seconds reflects live context (ticks_to_snapshot uses wall-clock elapsed)
4. ✅ Strategy evaluate() returns Signal on spike data (check 8)
5. ✅ Adapter populates all locked_* fields (checks 11-12)
6. ✅ Adapter populates executor-required signal_data keys (checks 13-14)
7. ✅ evaluate_strategies is async (check 3)
8. ✅ No modifications to executor/redeemer/balance (checks 16-17)
9. ✅ Module isolation — no analysis/core imports (check 18)
10. ✅ Empty ticks produces all-NaN (check 15)
11. ✅ Balance fetch failure path tested in T01 (adapter returns [] with warning)
12. ✅ Bad input → immediate TypeError/ValueError (pure function contract)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` | 0 | ✅ pass | <1s |
| 2 | `grep "from trading.strategy_adapter import evaluate_strategies" src/trading/main.py` | 0 | ✅ pass | <1s |
| 3 | `grep "from trading.strategies import evaluate_strategies" src/trading/main.py` (expect 0 matches) | 1 | ✅ pass | <1s |

## Diagnostics

- **Verification:** `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` — exit code 0 means full pipeline verified, exit code 1 means specific check(s) failed (each check prints PASS/FAIL with description)
- **Import check:** `grep "from trading.strategy_adapter" src/trading/main.py` — confirms the rewire
- **R009 integrity:** Checks 16-17 compare SHA-256 hashes against `/Users/igol/Documents/repo/polyedge/src/trading/{executor,redeemer,balance}.py` — any modification to those files will cause hash mismatch

## Deviations

None — executed exactly as planned.

## Known Issues

None.

## Files Created/Modified

- `src/trading/main.py` — MODIFIED: 1-line import change (`trading.strategies` → `trading.strategy_adapter`)
- `src/scripts/verify_s03.py` — NEW: 18-check contract verification script for S03 pipeline
- `.gsd/milestones/M001/slices/S03/tasks/T02-PLAN.md` — added Observability Impact section (pre-flight fix)
- `.gsd/milestones/M001/slices/S03/S03-PLAN.md` — marked T02 as `[x]` done
