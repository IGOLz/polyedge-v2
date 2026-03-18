---
slice: S03
milestone: M004
assessed_at: 2026-03-18T18:08:54+01:00
---

# Roadmap Reassessment After S03

## Changes Made

**S04 scope adjusted** from "Ranking & Output" to "Exit Simulation Fix & Output Display"

### Why

S03 delivered more than planned:
- **CSV columns already exist:** The results CSV from S03 already includes `stop_loss`, `take_profit`, and `exit_reason` columns (verified in S03-SUMMARY). S04's original primary deliverable (adding these columns) is complete.
- **Engine issue surfaced:** S03 identified that the data loader returns `market['ticks']` but the engine expects `market.get('prices')`, causing SL/TP simulation to be skipped. All trades show `exit_reason='resolution'` regardless of parameters passed.

### What Changed

**S04 now focuses on:**
1. **Fixing the market dict key mismatch** — prerequisite for actual SL/TP simulation
2. **Adding top 10 summary display** with explicit SL/TP values (original deliverable that's still needed)
3. **Verifying non-uniform exit_reason values** — proves SL/TP simulation actually runs

**Boundary map updated:**
- S03 → S04: Now produces results CSV with SL/TP columns (was originally S04's output)
- S04 → S05: Now produces fixed market dict and working SL/TP simulation (was originally just output formatting)

## Success-Criterion Coverage

All criteria still have clear owners:

- `Run python3 -m analysis.optimize --strategy S1 and see 100+ parameter combinations tested` → S03 ✓ (delivered)
- `Output CSV shows top 10 ranked by performance with explicit stop_loss and take_profit values` → S04 (top 10 display)
- `Each strategy (S1-S7) has complete get_param_grid() with SL/TP ranges` → S01 ✓ (delivered)
- `TEMPLATE demonstrates the pattern for new strategies` → S01 ✓ (delivered)
- `Trades distinguish SL exit vs TP exit vs hold-to-resolution in output` → S04 (fix simulation), S05 (verify)
- `Verification script proves all deliverables integrate correctly` → S05

## Requirement Coverage

**No change to requirement ownership.** Requirements remain sound:

- **R026** (Grid search generates Cartesian product including SL/TP dimensions) → Validated by S03 ✓
- **R027** (Backtest output CSV includes stop_loss, take_profit, exit_reason columns) → **Already delivered by S03** (can advance to validated)
- **R028** (Top 10 summary prints explicit SL/TP values) → Still owned by S04
- **R031** (Trades distinguish SL exit vs TP exit vs hold-to-resolution) → Partially delivered (field exists), S04 must make it functional

## Concrete Evidence

1. **S03-SUMMARY explicitly states:** "Results CSV at `results/optimization/Test_optimize_S1_Results.csv` includes stop_loss and take_profit columns with per-combination values"
2. **S03-SUMMARY documents the engine issue:** "Pre-existing engine issue (outside S03 scope): make_trade() looks for `market.get('prices')` but market dicts contain `'ticks'` not `'prices'`. This causes SL/TP simulator to be skipped."
3. **Verification output from S03:** All trades have `exit_reason='resolution'` because simulation doesn't run

## Conclusion

The roadmap adjustment is **minimal and necessary**. S04's work shifts from "add columns that don't exist" to "fix the engine so existing columns populate correctly." S05 verification remains unchanged. All success criteria still have clear paths to completion.
