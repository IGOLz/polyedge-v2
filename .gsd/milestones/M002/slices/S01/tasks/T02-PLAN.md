---
estimated_steps: 3
estimated_files: 1
---

# T02: Run 47-check verification and fix any issues

**Slice:** S01 — Apply unified report implementation and verify
**Milestone:** M002

## Description

Run `scripts/verify_reports.py` — the definitive 47-check validation suite for M002. It covers: import checks (StrategyReport from both paths), construction from metrics dict, JSON round-trip (write → read → compare), Markdown generation, live vs backtest field set parity (symmetric_difference), trade record handling (dataclass and dict forms), `compute_live_metrics` field parity with `engine.compute_metrics`, and edge cases (empty trades, single trade). The script mocks `py_clob_client` modules to avoid requiring the trading dependency chain.

## Steps

1. Run `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` and capture output
2. If any checks fail, diagnose the root cause (likely import chain or missing dependency) and fix
3. Confirm all 47 checks pass on a clean re-run

## Must-Haves

- [ ] All 47 checks in `verify_reports.py` pass
- [ ] No import errors or missing module failures
- [ ] JSON round-trip produces identical fields
- [ ] Backtest and live field sets have zero symmetric difference

## Verification

- `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` — output shows 47/47 checks passing, exit code 0

## Inputs

- `src/scripts/verify_reports.py` — 264-line verification script (restored in T01)
- `src/shared/strategies/report.py` — StrategyReport dataclass (restored in T01)
- `src/trading/report.py` — compute_live_metrics (restored in T01)
- `src/analysis/backtest/engine.py` — compute_metrics (schema source of truth)

## Observability Impact

- **Signals changed:** No new runtime signals. This task validates existing signals from the verify_reports.py suite.
- **Inspection surface:** `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` — outputs structured per-check ✓/✗ status and a final `N/47 checks passed` count line. Exit code 0 = all pass, non-zero = at least one failure with check name printed to stderr.
- **Failure visibility:** Import failures produce `ModuleNotFoundError` tracebacks with full module path. Field parity failures print the symmetric difference set. JSON round-trip failures show the differing keys/values.

## Expected Output

- Clean verification run: 47/47 checks pass
- If fixes were needed: modified source files with corrections documented
