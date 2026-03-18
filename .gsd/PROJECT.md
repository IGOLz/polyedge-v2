# PolyEdge

## What This Is

Unified Polymarket trading platform — data collection, strategy analysis, and live trading in a single monorepo. Four modules under `src/`: `shared` (config, DB, API, WebSocket), `core` (24/7 price collector), `analysis` (backtesting and strategy research), `trading` (live trading bot).

## Core Value

One strategy definition that works identically in backtesting and live trading — no divergence in logic, parameters, or time units.

## Current State

Project was consolidated from three separate repos (polyedge-core, polyedge-lab, polyedge-bot) into a unified monorepo. Each service has its own Dockerfile and runs in Docker Compose. Core collects price data 24/7 into TimescaleDB. Analysis runs backtests. Trading bot executes strategies live.

Strategies currently exist in three incompatible forms:
- `trading/strategies.py` — M3 (spike reversion) + M4 (volatility) as async functions operating on tick objects, using tick count as proxy for time
- `analysis/backtest/module_3_mean_reversion.py`, `module_4_volatility.py` — same strategies reimplemented with numpy arrays indexed by elapsed seconds
- `analysis/strategies/` — momentum, calibration, streak, farming backtests with their own data format and DB tables

## Architecture / Key Patterns

- `src/shared/` — config, asyncpg pool, models, API, WebSocket, HTTP helpers
- `src/core/` — market discovery, WS listener, tick recording, resolution polling (never touch)
- `src/analysis/` — backtest engine, data loader, strategy backtests (psycopg2/pandas)
- `src/trading/` — bot main loop, strategy evaluation, order execution, redemption (async)
- Docker Compose with 4 services: timescaledb, core, analysis, trading
- Core is isolated — never restarted on updates to analysis/trading

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [ ] M001: Unified Strategy Framework — shared strategy definitions consumed identically by analysis (backtest) and trading (live)
