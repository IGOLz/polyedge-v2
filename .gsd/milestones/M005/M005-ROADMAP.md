# M005: Optimization Overhaul

**Vision:** Transform the parameter optimizer from a sparse single-threaded prototype into a production-grade tool that explores millions of combinations per strategy using all CPU cores, with trailing stop loss, ROI metrics, rich reports, Windows compatibility, and complete CLI documentation.

## Success Criteria

- Every strategy's dry-run shows 1M+ parameter combinations including trailing SL variants
- Full optimization run for a strategy uses all CPU cores and produces a rich Markdown report
- Report contains top 5 by composite score, top 5 by PnL, top 5 by ROI with all relevant metrics
- ROI computed with configurable bet size ($10 default)
- No encoding errors on Windows (no non-ASCII in print/log output)
- CLI documentation covers every flag with examples

## Key Risks / Unknowns

- Memory pressure with millions of metric dicts in RAM — may need streaming or chunked aggregation
- Multiprocessing overhead for sharing market data across workers — need efficient serialization
- S7 has 10 parameters — fine-grained steps could produce unrunnable grid sizes; needs sensible capping

## Proof Strategy

- Memory/multiprocessing risk -> retire in S02 by proving a full optimization run completes for a strategy with 1M+ combos using multiprocessing without OOM
- S7 grid explosion -> retire in S01 by designing grids that stay in the 1M-10M range through strategic step sizing

## Verification Classes

- Contract verification: dry-run combo counts, grep for non-ASCII in print statements, docs file existence
- Integration verification: full optimization run completes, report file generated with correct sections
- Operational verification: runs on Windows without encoding errors
- UAT / human verification: user confirms report is readable and actionable

## Milestone Definition of Done

This milestone is complete only when all are true:

- All 7 strategies declare 1M+ parameter combinations (verified by dry-run)
- Trailing SL parameters (trailing_sl, trail_distance) present in all grids
- Full optimization run uses multiprocessing and completes without errors
- Rich Markdown report generated with top 5 by score, PnL, and ROI
- ROI metric present in metrics with configurable bet size
- Batched progress output (not per-combo config dump)
- No non-ASCII characters in print/log statements across analysis/ and shared/ Python files
- CLI documentation exists with all flags and examples
- Verification script proves all deliverables

## Requirement Coverage

- Covers: R034, R035, R036, R037, R038, R039, R040, R041, R042
- Partially covers: none
- Leaves for later: R033 (live trading SL/TP integration)
- Orphan risks: none

## Slices

- [ ] **S01: Windows Compatibility & Grid Expansion** `risk:medium` `depends:[]`
  > After this: dry-run for any strategy shows 1M+ combos (including trailing SL params), and all print/log output is ASCII-safe across the codebase.

- [ ] **S02: Parallel Engine with Trailing SL & ROI** `risk:high` `depends:[S01]`
  > After this: full optimization run uses all CPU cores, trailing SL is simulated in the engine, ROI metric computed, progress shows batched counters, metrics-only storage.

- [ ] **S03: Rich Reports & CLI Documentation** `risk:low` `depends:[S02]`
  > After this: optimization produces a rich Markdown report with top 5 by score/PnL/ROI, and comprehensive CLI docs exist with all flags and examples.

## Boundary Map

### S01 -> S02

Produces:
- `shared/strategies/S1-S7/config.py` — expanded param grids with 1M+ combos, including `trailing_sl` (bool) and `trail_distance` (float) parameter entries
- `shared/strategies/TEMPLATE/config.py` — updated template demonstrating trailing SL params
- ASCII-clean codebase — all print/log statements use only cp1252-safe characters

Consumes:
- nothing (first slice)

### S02 -> S03

Produces:
- `analysis/optimize.py` — rewritten optimizer with multiprocessing, batched progress output, metrics-only storage
- `analysis/backtest/engine.py` — `simulate_sl_tp_exit()` extended with trailing SL logic, `compute_metrics()` extended with ROI metric
- `analysis/backtest_strategies.py` — `run_strategy()` accepts `trailing_sl` and `trail_distance` params
- CLI flags: `--bet-size`, `--workers` (CPU count)
- Metrics dict shape: adds `roi`, `trailing_sl`, `trail_distance` fields

Consumes from S01:
- Expanded param grids with trailing SL parameters
- ASCII-safe print/log output

### S01 -> S03

Produces:
- Same as S01 -> S02 (S03 reads the expanded grids for documentation)

Consumes:
- nothing (first slice)

### S02 -> S03 (reporting)

Produces:
- Metrics DataFrame with ROI, trailing SL fields, all combo results
- `save_module_results()` adapted for metrics-only output

Consumes from S02:
- Full metrics DataFrame from optimizer run
- ROI field in metrics
