# PolyEdge

## What This Is

Unified Polymarket trading platform — data collection, strategy analysis, and live trading in a single monorepo. Four modules under `src/`: `shared` (config, DB, API, WebSocket, strategies), `core` (24/7 price collector), `analysis` (backtesting, strategy research, optimization), `trading` (live trading bot).

## Core Value

One strategy definition that works identically in backtesting and live trading — no divergence in logic, parameters, or time units.

## Current State

Project was consolidated from three separate repos (polyedge-core, polyedge-lab, polyedge-bot) into a unified monorepo. Each service has its own Dockerfile and runs in Docker Compose. Core collects price data 24/7 into TimescaleDB. Analysis runs backtests. Trading bot executes strategies live.

**M001 complete.** The unified strategy framework is fully operational. All 12 requirements validated, 11 decisions recorded.

**M003 complete.** Research-backed strategy overhaul — replaced disposable S1/S2 with 7 research-backed strategies for 5-minute crypto up/down markets, upgraded engine with dynamic Polymarket fees and slippage modeling, delivered operator playbook with 6-threshold deployment framework and comprehensive verification script proving all deliverables integrate correctly.

**M004 complete.** Parameter Grid Optimization with Stop Loss & Take Profit — transformed backtesting from fixed-parameter testing to exhaustive grid search with stop loss and take profit as universal exit parameters. All 7 strategies (S1-S7) now declare SL/TP parameter ranges in their config grids (3 values each, creating 9× multiplier on existing grid dimensions). Engine scans prices second-by-second with direction-specific threshold logic (Up: SL when price ≤ stop_loss, TP when price ≥ take_profit; Down: inverted thresholds). Trade dataclass extended with exit_reason field ('sl', 'tp', 'resolution'). Grid search orchestrator uses dataclass introspection to split parameter dicts and thread exit params through run_strategy() to make_trade(). Console and CSV output display explicit SL/TP values for all ranked combinations. Grid sizes range 648-1728 combinations per strategy. Verification script with 7 automated checks proves end-to-end integration. All 9 requirements (R023-R031) validated.

**M005 in progress.** Optimization Overhaul — expanding parameter grids from ~1000 to millions of combinations per strategy, adding multiprocessing parallelization, trailing stop loss, ROI metric, rich Markdown reports, Windows encoding fixes, and CLI documentation.

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

### What M003 Delivered

**S01 (Scaffolding):** 7 new strategy folders (S1-S7) with research-backed naming (calibration, momentum, reversion, volatility, time_phase, streak, composite), updated TEMPLATE with param grid support, registry discovery of all 8 strategies, verification script with 25 checks.

**S02 (Engine Upgrades):** Dynamic Polymarket fee formula (`base_rate × min(price, 1-price)`) peaking at ~3.15% for 50/50 markets, configurable slippage penalty adjusting entry prices, CLI controls (`--slippage`, `--fee-base-rate`), updated PnL calculations using dynamic fees, backward compatibility break (removed flat `fee_rate` parameter).

**S03 (Strategy Implementations):** All 7 strategies implemented with real signal detection:
- **S1 Calibration:** Exploits systematic mispricing near 50/50 prices (108 combinations)
- **S2 Momentum:** Detects directional velocity in first 30-60 seconds, fades strong moves (72 combinations)
- **S3 Mean Reversion:** Two-phase spike detection then reversion detection (144 combinations)
- **S4 Volatility Regime:** Enters contrarian under high volatility + extreme price (108 combinations)
- **S5 Time-Phase Entry:** Filters by elapsed time and hour-of-day (108 combinations)
- **S6 Streak/Sequence:** Intra-market consecutive price move detection (72 combinations)
- **S7 Composite Ensemble:** Voting across patterns, enters on consensus (192 combinations)

**S04 (Operator Playbook + Verification):** 1189-line playbook with per-strategy documentation, 18 metrics with formulas and thresholds, 6-threshold Go/No-Go framework, CLI reference, parameter optimization guide, troubleshooting for 6 failure modes, M003 milestone verification script with 8 check categories.

### What M004 Delivered

**S01 (Parameter Grid Foundation):** All 7 strategies (S1-S7) plus TEMPLATE declare stop_loss and take_profit parameter ranges in `get_param_grid()`. Strategy-specific ranges tuned to typical entry prices per D013. Grid sizes range 648-1728 combinations per strategy.

**S02 (Stop Loss & Take Profit Engine):** `simulate_sl_tp_exit()` function scanning prices second-by-second with direction-specific thresholds. Trade dataclass extended with `exit_reason` field. 13 comprehensive unit tests.

**S03 (Grid Search Orchestrator):** Extended optimize.py with dataclass introspection for separating config fields from exit params. Full Cartesian product grid search includes SL/TP dimensions.

**S04 (Exit Simulation Fix & Output Display):** Fixed market dict key mismatch. Enhanced console top 10 summary with explicit SL/TP values.

**S05 (Integration Verification):** Comprehensive verification script with 7 automated checks.

### Full Strategy Lifecycle

Create from TEMPLATE -> implement evaluate() -> add get_param_grid() -> backtest with `python3 -m analysis.backtest_strategies` -> optimize with `python3 -m analysis.optimize` -> deploy to live trading -> compare `reports/backtest/S1.json` vs `reports/live/S1.json`.

## Architecture / Key Patterns

- `src/shared/` — config, asyncpg pool, models, API, WebSocket, HTTP helpers
- `src/shared/strategies/` — base classes, registry, report model, S1-S7 strategies, TEMPLATE (folder-per-strategy auto-discovery)
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
bash scripts/verify_s03_strategies.sh                   # 42 checks — M003/S03 all strategies implemented
bash scripts/verify_m003_milestone.sh                   # 8 checks — M003 complete (exit 0 = all deliverables verified)
cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py # 8 strategy checks — M004/S01 parameter grids with SL/TP
cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v # 13 tests — M004/S02 SL/TP engine unit tests
bash scripts/verify_m004_milestone.sh                   # 7 checks — M004 complete (exit 0 = all deliverables verified)
```

## Milestone Sequence

- [x] M001: Unified Strategy Framework — shared strategy definitions consumed identically by analysis (backtest) and trading (live)
- [x] M002: Unified Strategy Reports — both backtest and live trading produce per-strategy reports in identical JSON + Markdown format
- [x] M003: Research-Backed Strategy Overhaul — replace disposable strategies with 7 real prediction market strategies, upgrade engine with dynamic fees + slippage
- [x] M004: Parameter Grid Optimization with Stop Loss & Take Profit — transform backtesting from fixed-parameter testing to exhaustive grid search across parameter combinations with SL/TP as universal exit parameters
- [ ] M005: Optimization Overhaul — expand grids to millions of combos, multiprocessing, trailing SL, rich reports, Windows compat, CLI docs
