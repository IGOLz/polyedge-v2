# PolyEdge

## What This Is

Unified Polymarket trading platform — data collection, strategy analysis, and live trading in a single monorepo. Four modules under `src/`: `shared` (config, DB, API, WebSocket, strategies), `core` (24/7 price collector), `analysis` (backtesting, strategy research, optimization), `trading` (live trading bot).

## Core Value

One strategy definition that works identically in backtesting and live trading — no divergence in logic, parameters, or time units.

## Current State

Project was consolidated from three separate repos (polyedge-core, polyedge-lab, polyedge-bot) into a unified monorepo. Each service has its own Dockerfile and runs in Docker Compose. Core collects price data 24/7 into TimescaleDB. Analysis runs backtests. Trading bot executes strategies live.

**M001 complete.** The unified strategy framework is fully operational. All 12 requirements validated, 11 decisions recorded.

**M002 complete.** Unified strategy reports — both analysis backtest and live trading produce per-strategy reports in identical JSON + Markdown format via `StrategyReport`.

**M003 in progress.** Research-backed strategy overhaul — replacing disposable S1/S2 with 7 research-backed strategies for 5-minute crypto up/down markets, plus engine upgrades for dynamic Polymarket fees and slippage modeling. S01 complete (scaffolding).

### What M001 Delivered

- **Shared strategy package** (`shared/strategies/`): base types (StrategyConfig, MarketSnapshot, Signal, BaseStrategy), folder-based auto-discovery registry, S1 (spike reversion), S2 (volatility), and TEMPLATE skeleton.
- **Analysis adapter** (`analysis/backtest_strategies.py`): bridges shared strategies into the existing backtest engine.
- **Trading adapter** (`trading/strategy_adapter.py`): bridges shared strategies into the trading bot. Zero modifications to executor/redeemer/balance.
- **Parity proof** (`scripts/parity_test.py`): 24 assertions proving identical signals on identical data.
- **Parameter optimizer** (`analysis/optimize.py`): grid-search with dry-run mode.

### What M002 Delivered

- **Shared report model** (`shared/strategies/report.py`): `StrategyReport` dataclass with 20+ metrics, JSON/Markdown serialization, `from_json()` loading. Same schema for both contexts.
- **Backtest reports**: `analysis/backtest_strategies.py` now generates per-strategy `{SID}.json` and `{SID}.md` in `reports/backtest/` alongside existing CSV output.
- **Live trading reports**: `trading/report.py` queries `bot_trades`, computes the full metric set (matching engine.compute_metrics), generates per-strategy reports in `reports/live/`.
- **Auto-generation**: Trading bot generates reports every hour via `strategy_report_loop`.

### What M003/S01 Delivered

- **7 new strategy folders** (`S1` through `S7`) in `shared/strategies/` with research-backed naming: S1_calibration, S2_momentum, S3_reversion, S4_volatility, S5_time_phase, S6_streak, S7_composite.
- **Updated TEMPLATE**: Added `get_param_grid()` function and updated README to make param grid a required component.
- **Registry discovery**: All 8 strategies (TEMPLATE + S1-S7) discovered via auto-discovery, each instantiates with correct metadata.
- **Stub implementations**: All strategies have `evaluate()` returning None and `get_param_grid()` returning `{}` with TODOs for S03.
- **Verification script**: `scripts/verify_s01_scaffolding.sh` with 25 checks proving scaffolding correctness.

### Full Strategy Lifecycle

Create from TEMPLATE → implement evaluate() → add get_param_grid() → backtest with `python3 -m analysis.backtest_strategies` → optimize with `python3 -m analysis.optimize` → deploy to live trading → compare `reports/backtest/S1.json` vs `reports/live/S1.json`.

## Architecture / Key Patterns

- `src/shared/` — config, asyncpg pool, models, API, WebSocket, HTTP helpers
- `src/shared/strategies/` — base classes, registry, report model, S1–S7 strategies, TEMPLATE (folder-per-strategy auto-discovery)
- `src/core/` — market discovery, WS listener, tick recording, resolution polling (never touch)
- `src/analysis/` — backtest engine (with dynamic fees + slippage), data loader, strategy backtests, optimizer (psycopg2/pandas)
- `src/trading/` — bot main loop, strategy evaluation via shared adapter, order execution, redemption, report generation (async)
- Docker Compose with 4 services: timescaledb, core, analysis, trading
- Core is isolated — never restarted on updates to analysis/trading

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Authoritative Diagnostics

```bash
cd src && PYTHONPATH=. python3 scripts/verify_s01.py    # 18 checks — shared framework
cd src && PYTHONPATH=. python3 scripts/verify_s02.py    # 18 checks — analysis adapter
cd src && PYTHONPATH=. python3 scripts/verify_s03.py    # 18 checks — trading adapter
cd src && PYTHONPATH=. python3 scripts/parity_test.py   # 24 checks — signal parity proof
cd src && PYTHONPATH=. python3 scripts/verify_reports.py # 47 checks — unified reports
bash scripts/verify_s01_scaffolding.sh                  # 25 checks — M003/S01 strategy scaffolding
```

## Milestone Sequence

- [x] M001: Unified Strategy Framework — shared strategy definitions consumed identically by analysis (backtest) and trading (live)
- [x] M002: Unified Strategy Reports — both backtest and live trading produce per-strategy reports in identical JSON + Markdown format
- [ ] M003: Research-Backed Strategy Overhaul — replace disposable strategies with 7 real prediction market strategies, upgrade engine with dynamic fees + slippage (S01 complete: scaffolding)
