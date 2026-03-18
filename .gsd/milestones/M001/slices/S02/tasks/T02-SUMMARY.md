---
id: T02
parent: S02
milestone: M001
provides:
  - Contract verification script for the S02 analysis adapter pipeline (18 checks, no DB required)
key_files:
  - src/scripts/verify_s02.py
key_decisions:
  - Synthetic price data uses explicit array values (not loops) for spike+reversion to ensure S1 thresholds are met with margin
patterns_established:
  - Verify_s02 follows verify_s01 pattern: numbered checks, [PASS]/[FAIL] output, summary, exit code 0/1
observability_surfaces:
  - Exit code 0/1 from verify_s02.py serves as a CI-ready adapter health check
  - Each numbered check identifies the exact failing pipeline stage (import/conversion/evaluation/trade/integration/isolation)
duration: 12m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T02: Create contract verification script for S02

**Created verify_s02.py with 18 pipeline checks covering import, conversion, strategy evaluation, trade creation, metrics, integration, and module isolation — all passing on synthetic data without DB**

## What Happened

Created `src/scripts/verify_s02.py` following the established `verify_s01.py` pattern. The script builds synthetic market data with a carefully calibrated spike+reversion price curve that triggers S1's detection thresholds, then runs the full adapter pipeline: `market_to_snapshot` → `strategy.evaluate` → `make_trade` → `compute_metrics` → `run_strategy` integration.

Initial synthetic data (gradual ramp over 15 seconds) failed to produce a signal — the reversion amount was too small within S1's `min_reversion_ticks=10` window. Redesigned the price curve: spike to 0.85 in 5 seconds, hold briefly, then sharp drop to 0.75 within the reversion window. This produces reversion=0.106 at s=10 (well within threshold) and entry_price=0.24 (well within 0.35 threshold).

## Verification

All 18 checks pass with exit code 0:
- Checks 1-3: imports from adapter, shared strategies, and engine
- Checks 4-7: market_to_snapshot conversion (MarketSnapshot type, prices shape, elapsed_seconds, metadata)
- Checks 8-11: S1 strategy evaluation (Signal returned, direction='Down', reversion_second=10)
- Checks 12-15: Trade pipeline (make_trade, direction match, compute_metrics keys, total_bets=1)
- Checks 16-18: Integration (run_strategy produces trades, module isolation — no trading/core imports)

Slice-level verification (2 of 3 pass, 1 requires DB):
1. `verify_s02.py` — ✅ all 18 checks pass, exit 0
2. `--strategy S1` with real DB — ⏭ requires DB connection (expected for worktree)
3. Empty-market diagnostic — ✅ zero markets produces total_bets=0 without error

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` | 0 | ✅ pass | 1s |
| 2 | `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --help` | 0 | ✅ pass | <1s |
| 3 | `cd src && PYTHONPATH=. python3 -c "...empty-market diagnostic..."` | 0 | ✅ pass | <1s |

## Diagnostics

- Run `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` to check full adapter pipeline health
- Each check has a numbered label — first `[FAIL]` identifies the broken stage
- Exit code 0 = all healthy, 1 = regression detected

## Deviations

Synthetic price data redesigned from the plan's loop-based gradual ramp to explicit array values with a sharper reversion curve. The plan's formula produced reversion amounts of only ~0.08 within S1's `min_reversion_ticks=10` window, insufficient to trigger the 0.10 threshold. The fix uses a faster spike (5 seconds to peak) and sharper drop (0.85→0.75 in 3 steps), giving ample margin.

## Known Issues

None.

## Files Created/Modified

- `src/scripts/verify_s02.py` — New: 18-check contract verification script for S02 adapter pipeline
- `.gsd/milestones/M001/slices/S02/tasks/T02-PLAN.md` — Added Observability Impact section (pre-flight fix)
