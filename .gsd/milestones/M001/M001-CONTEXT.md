# M001: Unified Strategy Framework

**Gathered:** 2026-03-18
**Status:** Ready for planning

## Project Description

PolyEdge is a Polymarket trading platform that collects crypto market price data (core), backtests trading strategies (analysis), and executes them live (trading). Currently strategies are defined separately in analysis and trading with different data formats, time units, and parameters — leading to divergence between what backtests show and what production does.

## Why This Milestone

The same strategy logic exists in three incompatible forms. Trading uses tick indices as a proxy for seconds. Analysis uses proper seconds-indexed numpy arrays. Parameters are hardcoded in different places. When a strategy is tuned in backtesting, those changes don't propagate to live trading without manual reimplementation. The user plans to write many new strategies — doing that in the current split architecture would multiply the divergence.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Create a new strategy by copying a template folder into `shared/strategies/S_new/`, writing config + evaluate logic once
- Run that strategy in backtesting (`python -m analysis.backtest_strategies --strategy S_new`) and see results
- Enable that strategy in the live trading bot and know it behaves identically to the backtest
- Run parameter optimization (`python -m analysis.optimize --strategy S1`) to grid-search the config space

### Entry point / environment

- Entry point: CLI commands for analysis, Docker service for trading
- Environment: Docker Compose (timescaledb + core + analysis + trading)
- Live dependencies involved: TimescaleDB (shared), Polymarket CLOB API (trading only)

## Completion Class

- Contract complete means: shared strategy interface exists, strategies load from registry, adapters convert data correctly
- Integration complete means: analysis backtest runner and trading bot both consume shared strategies and produce consistent results
- Operational complete means: trading bot runs with shared strategies in Docker without regressions

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A strategy defined in `shared/strategies/S1/` can be backtested via `analysis` and produces results
- The same strategy can be evaluated live via `trading` and produces Signal objects the executor accepts
- Given identical price data, both paths produce identical signals (parity test)
- A new strategy can be created from the template and immediately works in both contexts

## Risks and Unknowns

- **Data normalization complexity** — live ticks arrive at irregular intervals; converting them to a seconds-indexed snapshot that matches the backtest format requires interpolation or nearest-neighbor logic. If this is wrong, parity breaks.
- **Trading executor coupling** — the executor currently imports Signal from `trading.strategies` and expects specific `signal_data` fields. Changing the Signal shape could break execution.
- **Async vs sync boundary** — trading is async, analysis is sync (psycopg2/pandas). The shared strategy evaluate function must work in both contexts without `await`.

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R001 — unified strategy definition (this milestone's primary goal)
- R003 — normalized seconds-indexed data (fixes the tick-vs-seconds bug)
- R007 — identical behavior guarantee (the acceptance criterion)
- R009, R010 — constraints: don't touch executor/redeemer/balance or core

## Scope

### In Scope

- `shared/strategies/` folder with base classes, registry, per-strategy configs
- MarketSnapshot data model (seconds-indexed prices)
- Signal dataclass in shared
- Analysis adapter (historical data → MarketSnapshot → strategy → results)
- Trading adapter (live ticks → MarketSnapshot → strategy → Signal)
- Porting M3 + M4 as S1 + S2 to prove the framework
- Strategy template folder with documentation
- Parameter optimization script

### Out of Scope / Non-Goals

- Rewriting M3/M4 strategy logic or parameters (they're disposable)
- Changing the trading executor, redeemer, balance checker, or DB tables
- Modifying core in any way
- Migrating the `analysis/main.py` statistical analysis (calibration, trajectory, time-of-day) — those aren't strategies
- Migrating `analysis/strategies/` old-style backtests (momentum, calibration, streak, farming) — those can coexist and be migrated later if desired

## Technical Constraints

- Strategy evaluate functions must be synchronous (no `await`) so they work in both async trading and sync analysis contexts
- MarketSnapshot must use elapsed seconds as the time axis, not tick indices or datetime objects
- Signal must be backward-compatible with what `trading/executor.py` expects (direction, strategy_name, entry_price, signal_data dict, locked_shares, locked_cost, etc.)
- Analysis uses psycopg2 + pandas (sync); trading uses asyncpg (async). Shared code cannot depend on either.

## Integration Points

- `trading/executor.py` — consumes Signal objects; the new shared Signal must match its expectations
- `trading/main.py` — currently calls `evaluate_strategies()` from `trading/strategies.py`; will be rewired to call through the shared registry
- `analysis/backtest/data_loader.py` — produces seconds-indexed numpy arrays; the analysis adapter builds MarketSnapshot from this
- `analysis/backtest/engine.py` — computes metrics from Trade objects; the analysis adapter feeds it results from shared strategies
- `trading/db.py` — `get_market_ticks()` returns `list[Tick]`; the trading adapter converts these to MarketSnapshot

## Open Questions

- None blocking — scope is clear.
