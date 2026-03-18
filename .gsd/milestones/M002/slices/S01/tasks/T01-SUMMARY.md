---
id: T01
parent: S01
milestone: M002
provides:
  - Full src/ directory tree with M001 foundation and M002 report implementation
  - All Python imports for the report pipeline resolve successfully
key_files:
  - src/shared/strategies/report.py
  - src/shared/strategies/base.py
  - src/shared/strategies/registry.py
  - src/shared/strategies/S1/
  - src/shared/strategies/S2/
  - src/shared/strategies/TEMPLATE/
  - src/analysis/backtest_strategies.py
  - src/trading/report.py
  - src/scripts/verify_reports.py
key_decisions:
  - Converted 12 symlinks in src/trading/ and src/shared/ to real file copies for worktree self-containment
patterns_established:
  - Worktree source restoration via git checkout <commit> -- <path> followed by symlink-to-file conversion
observability_surfaces:
  - verify_reports.py outputs structured 47-check pass/fail with per-check names
  - Standard Python import errors surface missing files via ModuleNotFoundError
duration: 5m
verification_result: passed
completed_at: 2026-03-18T12:45Z
blocker_discovered: false
---

# T01: Restore source tree from implementation commit

**Restored full src/ tree (41 files) from commit 777a474 with 12 symlinks converted to real copies; all 47 verification checks pass**

## What Happened

The working tree had only `.gsd/` metadata with no `src/` files. Ran `git checkout 777a474 -- src/` to restore the full source tree. Found 12 symlinks (in `src/trading/` and `src/shared/db.py`) pointing to the main repo's absolute paths — converted all to real file copies so the worktree is self-contained. Verified all M001 foundation imports (`BaseStrategy`, `discover_strategies`) and M002 report imports (`StrategyReport`) succeed. Ran the 47-check verification script — all passed.

## Verification

- `ls` confirmed all key files exist on disk with expected line counts (report.py: 310, trading/report.py: 379, verify_reports.py: 264)
- `from shared.strategies.report import StrategyReport` — import succeeds
- `from shared.strategies import StrategyReport` — re-export succeeds, all 29 dataclass fields visible
- `grep -c '_generate_reports' src/analysis/backtest_strategies.py` — returns 2
- `verify_reports.py` — 47/47 checks pass (imports, construction, JSON round-trip, markdown, live context parity, trade records, edge cases)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `ls src/shared/strategies/report.py src/trading/report.py src/scripts/verify_reports.py` | 0 | ✅ pass | <1s |
| 2 | `cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; print('OK')"` | 0 | ✅ pass | <1s |
| 3 | `cd src && PYTHONPATH=. python3 -c "from shared.strategies import StrategyReport; print(sorted(StrategyReport.__dataclass_fields__.keys()))"` | 0 | ✅ pass | <1s |
| 4 | `grep -c '_generate_reports' src/analysis/backtest_strategies.py` | 0 | ✅ pass | <1s |
| 5 | `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` | 0 | ✅ pass (47/47) | 1s |
| 6 | `cd src && PYTHONPATH=. python3 -c "...StrategyReport(...); d = r.to_dict(); print(d['strategy_id'], type(d))"` | 0 | ✅ pass | <1s |

## Diagnostics

- **File inventory:** `find src -type f | wc -l` → 41 files total (27 Python + 14 other)
- **Symlink check:** `find src -type l | wc -l` → 0 (all converted)
- **Import smoke test:** `cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; print('OK')"`
- **Full verification:** `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` → 47/47 pass

## Deviations

None. All steps executed as planned.

## Known Issues

None.

## Files Created/Modified

- `src/` — Full directory tree restored from commit 777a474 (41 files)
- `src/shared/db.py` — Converted from symlink to real file
- `src/trading/__init__.py` — Converted from symlink to real file
- `src/trading/balance.py` — Converted from symlink to real file
- `src/trading/config.py` — Converted from symlink to real file
- `src/trading/constants.py` — Converted from symlink to real file
- `src/trading/db.py` — Converted from symlink to real file
- `src/trading/executor.py` — Converted from symlink to real file
- `src/trading/main.py` — Converted from symlink to real file
- `src/trading/redeemer.py` — Converted from symlink to real file
- `src/trading/setup.py` — Converted from symlink to real file
- `src/trading/strategies.py` — Converted from symlink to real file
- `src/trading/utils.py` — Converted from symlink to real file
- `.gsd/milestones/M002/slices/S01/S01-PLAN.md` — Added Observability/Diagnostics section, failure-path check, marked T01 done
- `.gsd/milestones/M002/slices/S01/tasks/T01-PLAN.md` — Added Observability Impact section
