# S01: Apply unified report implementation and verify

**Goal:** Get all M002 implementation code from commit `777a474` onto the working tree and verify the full report pipeline works — imports, construction, serialization, field parity.
**Demo:** `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` passes 47/47 checks.

## Must-Haves

- All M001 foundation files present on disk (base.py, registry.py, S1/, S2/, TEMPLATE/)
- `shared/strategies/report.py` — StrategyReport dataclass with 20+ metrics, JSON/Markdown serialization
- `analysis/backtest_strategies.py` — `_generate_reports()` producing per-strategy reports
- `trading/report.py` — `compute_live_metrics()` with engine-parity field set
- `scripts/verify_reports.py` — 47-check verification passing

## Observability / Diagnostics

- **Runtime signals:** `verify_reports.py` outputs a structured pass/fail count (`47/47 checks passed`) and prints each check name with ✓/✗ status to stdout. Any failure prints the check name and reason to stderr.
- **Inspection surfaces:** After restoration, `find src -type f -name '*.py' | wc -l` gives a quick file-count sanity check. `python3 -c "from shared.strategies.report import StrategyReport; print(StrategyReport.__dataclass_fields__.keys())"` shows all report fields.
- **Failure visibility:** Import failures produce standard Python tracebacks with module path and line number. `verify_reports.py` exits non-zero on any check failure and names the failing check.
- **Redaction constraints:** No secrets or credentials in any restored source file. Report data uses synthetic/mock values in verification.

## Verification

- `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` — all 47 checks pass
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; print('OK')"` — import succeeds
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies import StrategyReport; print(StrategyReport.__dataclass_fields__.keys())"` — all fields visible
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; r = StrategyReport(strategy_id='test', strategy_name='X', context='backtest'); d = r.to_dict(); print(d['strategy_id'], type(d))"` — failure-path: confirms construction with minimal args and dict serialization

## Tasks

- [x] **T01: Restore source tree from implementation commit** `est:15m`
  - Why: The working tree is empty — all implementation exists in commit `777a474` but hasn't been applied to HEAD. Both M001 foundation files and M002 new files must be on disk for any imports to work.
  - Files: All files under `src/` from commit `777a474`
  - Do: Checkout the full `src/` tree from `777a474`. Ensure all shared/strategies files, analysis adapter, trading report module, and verification script are present. Resolve any symlinks by converting them to real files where needed for the working tree.
  - Verify: `ls src/shared/strategies/report.py src/trading/report.py src/scripts/verify_reports.py` — all exist; `cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; print('OK')"` — import succeeds
  - Done when: `find src -type f | wc -l` shows all expected files and StrategyReport is importable

- [x] **T02: Run 47-check verification and fix any issues** `est:15m`
  - Why: The verification script is the definitive validation that the report pipeline works — imports, construction, JSON round-trip, markdown generation, field parity between backtest and live contexts, and edge cases.
  - Files: `src/scripts/verify_reports.py`
  - Do: Run the verification script. If any checks fail, diagnose and fix. The script mocks `py_clob_client` to avoid requiring the trading dependency chain. All 47 checks must pass.
  - Verify: `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` — 47/47 pass
  - Done when: All 47 checks pass with zero failures

## Files Likely Touched

- `src/shared/strategies/report.py` (restored from 777a474)
- `src/shared/strategies/__init__.py` (restored from 777a474)
- `src/shared/strategies/base.py` (restored from 777a474 — M001 dependency)
- `src/shared/strategies/registry.py` (restored from 777a474 — M001 dependency)
- `src/shared/strategies/S1/` (restored from 777a474 — M001 dependency)
- `src/shared/strategies/S2/` (restored from 777a474 — M001 dependency)
- `src/shared/strategies/TEMPLATE/` (restored from 777a474 — M001 dependency)
- `src/analysis/backtest_strategies.py` (restored from 777a474)
- `src/trading/report.py` (restored from 777a474)
- `src/scripts/verify_reports.py` (restored from 777a474)
