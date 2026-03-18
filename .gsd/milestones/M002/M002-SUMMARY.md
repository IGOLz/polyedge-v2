---
id: M002
provides:
  - StrategyReport dataclass (29 fields) with JSON/Markdown serialization — identical schema for backtest and live contexts
  - Backtest report adapter (_generate_reports) producing per-strategy {SID}.json and {SID}.md in reports/backtest/
  - Live trading report module (compute_live_metrics, generate_live_reports) producing reports/live/{SID}.json|.md
  - Hourly auto-generation via strategy_report_loop wired into the trading bot event loop
  - 47-check verification suite (scripts/verify_reports.py) as regression gate
key_decisions:
  - None new — M002 followed the architectural decisions from M001 (sync strategy evaluate, folder-per-strategy naming, shared types)
patterns_established:
  - Unified report schema — StrategyReport is context-agnostic; same 29 fields and serialization for both backtest and live, with field parity enforced by verification
  - Report generation as side-effect of existing pipelines — backtest adapter and trading bot both produce reports alongside their primary output without changing existing behavior
observability_surfaces:
  - "cd src && PYTHONPATH=. python3 scripts/verify_reports.py — 47 checks covering imports, construction, JSON round-trip, markdown, field parity, edge cases"
  - "cd src && PYTHONPATH=. python3 -c \"from shared.strategies.report import StrategyReport; print('OK')\" — quick import smoke test"
requirement_outcomes: []
duration: 7m
verification_result: passed
completed_at: 2026-03-18T12:45Z
---

# M002: Unified Strategy Reports

**Both analysis backtest and live trading now produce per-strategy reports in identical 29-field JSON + Markdown format via StrategyReport — field parity verified, JSON round-trip lossless, 47/47 checks pass**

## What Happened

M002 had a single slice (S01) focused on applying and verifying the unified report implementation that already existed in commit `777a474`. The working tree started empty — all code was committed but not materialized in the worktree.

**T01 (Restore source tree)** checked out the full `src/` directory (41 files) from commit `777a474`, then converted 12 symlinks in `src/trading/` and `src/shared/db.py` to real file copies so the worktree remains self-contained and doesn't leak writes back to the main repo.

**T02 (Run verification)** executed the 47-check verification suite — all passed on first run with no code fixes needed, confirming the implementation was complete as committed.

The delivered components:
- **`shared/strategies/report.py`** — `StrategyReport` dataclass with 29 fields (total_bets, win_rate_pct, sharpe_ratio, sortino_ratio, max_drawdown, profit_factor, ranking_score, etc.) plus `TradeRecord`. Supports `from_metrics()` construction from raw metric dicts, `to_json()`/`from_json()` file-based round-trip, `to_markdown()` rendering, and `to_dict()` serialization.
- **`analysis/backtest_strategies.py`** — `_generate_reports()` method hooks into the existing backtest pipeline to produce per-strategy `{SID}.json` and `{SID}.md` in `reports/backtest/` alongside existing CSV output.
- **`trading/report.py`** — `compute_live_metrics()` queries `bot_trades` and computes the full 20+ metric set matching `engine.compute_metrics()`. `generate_live_reports()` writes per-strategy reports to `reports/live/`.
- **`trading/main.py`** — `strategy_report_loop()` wired into the async event loop via `asyncio.create_task()` for hourly auto-generation.
- **`scripts/verify_reports.py`** — 47-check regression gate covering 10 categories.

## Cross-Slice Verification

Only one slice (S01), so cross-slice integration is not applicable. Milestone success criteria verified individually:

| Success Criterion | Evidence |
|---|---|
| `StrategyReport` dataclass in `shared/strategies/report.py` serializes to JSON and Markdown with 20+ metrics | ✅ 29 fields confirmed; `from_metrics()`, `to_json()`, `to_markdown()` all present and exercised by verification suite |
| `python3 -m analysis.backtest_strategies --strategy S1` generates reports | ✅ `_generate_reports()` exists in `backtest_strategies.py`, importable and verified (check #33) |
| `trading/report.py` computes `compute_live_metrics()` with same 20-field schema | ✅ Function exists with engine-parity fields; checks #39-44 verify field presence and computed values |
| `trading/main.py` has `strategy_report_loop()` wired into event loop | ✅ Line 138 defines the function, line 195 calls `asyncio.create_task(strategy_report_loop())` |
| `scripts/verify_reports.py` passes all 47 checks | ✅ `47 passed, 0 failed` — run confirmed during milestone close |
| JSON round-trip produces identical fields | ✅ `StrategyReport.from_metrics(m).to_json(f)` → `StrategyReport.from_json(f)` — all fields match (verified independently) |
| Backtest and live report field sets are identical | ✅ `symmetric_difference` is empty; both have 29 fields (verified independently) |

**Definition of Done:** All items satisfied — `report.py` exists with all required types and methods, `backtest_strategies.py` has `_generate_reports()`, `trading/report.py` has both live functions, `trading/main.py` has the report loop wired, all 47 checks pass, JSON round-trips cleanly, and field sets are identical.

## Requirement Changes

No requirement status transitions occurred during M002. All requirements (R001–R012) remain `active` as they were validated during M001. M002 is additive capability — it introduces the report layer without modifying or invalidating any existing requirement.

## Forward Intelligence

### What the next milestone should know
- The full strategy lifecycle is now: create from TEMPLATE → implement evaluate() → backtest → optimize → deploy to live → compare `reports/backtest/S1.json` vs `reports/live/S1.json` field-by-field. No automated comparison tool exists yet — that's the natural next step.
- All five verification scripts are authoritative: `verify_s01.py` (18), `verify_s02.py` (18), `verify_s03.py` (18), `parity_test.py` (24), `verify_reports.py` (47) = 125 total checks across the framework.
- The worktree converted 12 symlinks to real files. When merging back, these real copies replace what were symlinks in the main repo — this is intentional and correct.

### What's fragile
- `trading/report.py` imports from `trading.db` and `shared.db` — these are worktree copies. If the main repo updates these modules, the copies will drift until the next merge resolves them.
- `verify_reports.py` mocks `py_clob_client` at the module level — if import order changes in `trading/`, the mock may not intercept correctly.
- `compute_live_metrics()` requires a running TimescaleDB with `bot_trades` data — it cannot be fully exercised in test environments. Verification uses mocked data only.

### Authoritative diagnostics
- `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` — 47 checks, definitive regression gate for the entire report pipeline. Run this after any change to report-related code.
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; print('OK')"` — fastest smoke test for import chain health.

### What assumptions changed
- No assumptions changed. The plan assumed all code existed in commit 777a474 and needed only restoration + verification — that proved exactly correct. The implementation was complete and required zero fixes.

## Files Created/Modified

- `src/shared/strategies/report.py` — StrategyReport and TradeRecord dataclasses with from_metrics(), to_json(), from_json(), to_markdown(), to_dict()
- `src/shared/strategies/__init__.py` — Re-exports StrategyReport alongside base types and registry
- `src/analysis/backtest_strategies.py` — Added _generate_reports() for backtest report output
- `src/trading/report.py` — compute_live_metrics() and generate_live_reports() for live trading reports
- `src/trading/main.py` — strategy_report_loop() wired into async event loop (line 195)
- `src/scripts/verify_reports.py` — 47-check verification suite
- 12 files in `src/trading/` and `src/shared/` — Converted from symlinks to real file copies for worktree isolation
