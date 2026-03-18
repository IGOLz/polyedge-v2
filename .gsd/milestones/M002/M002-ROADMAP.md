# M002: Unified Strategy Reports

**Vision:** Both analysis backtest and live trading produce per-strategy reports in identical JSON + Markdown format, so an agent can load `reports/backtest/S1.json` and `reports/live/S1.json` and compare field-by-field.

## Success Criteria

- `StrategyReport` dataclass in `shared/strategies/report.py` serializes to JSON and Markdown with 20+ metrics matching the `engine.compute_metrics()` field set
- `python3 -m analysis.backtest_strategies --strategy S1` generates `reports/backtest/S1.json` and `reports/backtest/S1.md` alongside existing CSV output
- `trading/report.py` computes `compute_live_metrics()` with the same 20-field schema as the backtest engine and generates `reports/live/{SID}.json|.md`
- `trading/main.py` has `strategy_report_loop()` wired into the bot's event loop for hourly auto-generation
- `scripts/verify_reports.py` passes all 47 checks (imports, construction, JSON round-trip, markdown, field parity, edge cases)

## Key Risks / Unknowns

- **M001 foundation must be on disk** — `shared/strategies/__init__.py` imports `base`, `registry`, and `report` together; if M001 files are missing, all imports fail before `report.py` is reached. The implementation code exists in commit `777a474` but the working tree is empty.

## Proof Strategy

- M001 dependency → retire in S01/T01 by restoring all source files from `777a474` and confirming `from shared.strategies import StrategyReport` succeeds

## Verification Classes

- Contract verification: `scripts/verify_reports.py` — 47 checks covering imports, construction, JSON round-trip, markdown generation, live metrics field parity, edge cases (empty/single trade)
- Integration verification: Backtest adapter `_generate_reports()` produces files in `reports/backtest/`; trading `generate_live_reports()` import chain resolves (live DB not available in test env)
- Operational verification: `strategy_report_loop()` wiring in `trading/main.py` confirmed by grep (live bot not exercised)
- UAT / human verification: none

## Milestone Definition of Done

This milestone is complete only when all are true:

- `shared/strategies/report.py` exists with `StrategyReport`, `TradeRecord`, `from_metrics()`, `from_json()`, `to_json()`, `to_markdown()`
- `analysis/backtest_strategies.py` contains `_generate_reports()` that produces per-strategy JSON+MD reports
- `trading/report.py` contains `compute_live_metrics()` and `generate_live_reports()` with engine-parity metrics
- `trading/main.py` has `strategy_report_loop()` wired into the async event loop
- `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` passes all 47 checks
- JSON round-trip: `StrategyReport.from_metrics(m).to_json(f)` → `StrategyReport.from_json(f)` produces identical fields
- Backtest and live report field sets are identical (symmetric_difference is empty)

## Requirement Coverage

- Covers: none of the existing R001–R013 requirements are directly about unified reports (those were all M001 requirements already validated)
- This milestone is additive capability extending the M001 framework — it introduces the report layer without modifying any existing requirement
- Leaves for later: agent-side comparison tooling, historical report versioning, dashboard/UI
- Orphan risks: none — all active requirements (R001–R012) were validated in M001

## Slices

- [x] **S01: Apply unified report implementation and verify** `risk:low` `depends:[]`
  > After this: `cd src && PYTHONPATH=. python3 scripts/verify_reports.py` passes 47/47 checks — StrategyReport constructs from metrics, round-trips through JSON, generates Markdown, and backtest/live field sets are identical

## Boundary Map

### S01

Produces:
- `shared/strategies/report.py` — `StrategyReport` and `TradeRecord` dataclasses with `from_metrics()`, `from_json()`, `to_json()`, `to_markdown()` serialization
- `analysis/backtest_strategies.py` updated with `_generate_reports()` producing `reports/backtest/{SID}.json|.md`
- `trading/report.py` — async module with `compute_live_metrics()` and `generate_live_reports()` producing `reports/live/{SID}.json|.md`
- `scripts/verify_reports.py` — 47-check verification suite as regression gate

Consumes:
- M001 foundation: `shared/strategies/base.py`, `registry.py`, `__init__.py`, S1/, S2/, TEMPLATE/ (must be on disk for imports)
- `analysis/backtest/engine.py` — `compute_metrics()` field set is the schema contract that `StrategyReport` mirrors
- `trading/main.py` — already has `strategy_report_loop()` wired (symlink to main repo)
