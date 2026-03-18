# M003: Research-Backed Strategy Overhaul

**Vision:** Replace disposable proof-of-concept strategies with 5-7 research-backed strategies for 5-minute crypto up/down prediction markets, upgrade the engine with realistic Polymarket fee dynamics and slippage modeling, and deliver an operator playbook so the user can independently evaluate each strategy's profitability and decide what to deploy live.

## Success Criteria

- Old S1/S2 strategy folders are deleted; 5-7 new strategy folders exist in `shared/strategies/`
- TEMPLATE updated to reflect new strategy shape (config with param grid, slippage-aware signal metadata)
- `engine.py` uses Polymarket dynamic fee formula instead of flat 2%; fee varies by entry price
- `engine.py` applies configurable slippage penalty to entry prices
- Each strategy is individually runnable: `python3 -m analysis.backtest_strategies --strategy SID` produces JSON + Markdown reports
- Running all strategies produces a comparative ranking table
- Operator playbook exists at `src/docs/STRATEGY_PLAYBOOK.md` with per-strategy commands, metric definitions, and profitability thresholds
- Verification script passes covering imports, construction, registry discovery, and backtest execution for all new strategies

## Key Risks / Unknowns

- **Dynamic fee formula precision** — Polymarket's exact base rate for short-term crypto markets isn't publicly documented with precision. Will implement the documented CLOB formula with a configurable base rate.
- **Streak strategy data density** — Needs consecutive same-asset markets. May produce too few trades for statistical significance depending on DB contents.
- **No guaranteed edge** — Some strategies may not be profitable. That's the correct outcome — the point is to discover this, not guarantee profitability.

## Proof Strategy

- Fee formula accuracy → retire in S02 by showing fee varies by price and matches documented formula shape
- Strategy viability → retire in S03 by running all strategies against real DB data; even zero-trade strategies are valid if the playbook explains why
- End-to-end usability → retire in S04 by copy-pasting playbook commands and getting expected output

## Verification Classes

- Contract verification: verification script covering imports, construction, registry discovery, param grids, signal generation on synthetic data
- Integration verification: each strategy runs through `backtest_strategies.py` against real DB data without errors
- Operational verification: playbook commands work when copy-pasted; output matches playbook descriptions
- UAT / human verification: user runs backtests and interprets results (not gated — user does this at their own pace after milestone completes)

## Milestone Definition of Done

This milestone is complete only when all are true:

- Old S1, S2 deleted from `shared/strategies/`
- 5-7 new strategy folders exist with real `evaluate()` implementations (not stubs)
- TEMPLATE updated for new strategy shape
- `engine.py` dynamic fee formula produces different fees at different price levels
- `engine.py` slippage penalty is configurable and affects reported PnL
- `python3 -m analysis.backtest_strategies --strategy SID` runs for each strategy without error
- `python3 -m analysis.backtest_strategies` (all strategies) produces a comparative ranking
- Operator playbook exists with per-strategy CLI commands, metric interpretation guide, and go/no-go thresholds
- Verification script passes all checks
- `src/core/` is unmodified (R010)

## Requirement Coverage

- Covers: R014, R015, R016, R017, R018, R019, R020, R021, R022
- Partially covers: R002, R005, R008, R011 (extends these with new strategy content)
- Leaves for later: R006 (trading bot integration — user decides after seeing results), R007 (parity re-verification after new strategies)
- Orphan risks: none — all active requirements are mapped

## Slices

- [x] **S01: Clean slate + strategy scaffolding** `risk:low` `depends:[]`
  > After this: Old S1/S2 deleted, TEMPLATE updated, 7 empty strategy folders with config stubs and `__init__.py` created. Registry discovers all 7 (with no-op evaluate returning None).

- [x] **S02: Engine upgrades — dynamic fees + slippage** `risk:medium` `depends:[]`
  > After this: `make_trade()` applies Polymarket dynamic fee formula and configurable slippage. Running a backtest with `--slippage 0.01` vs `--slippage 0` produces different PnL. Fee at price=0.50 is higher than fee at price=0.10.

- [ ] **S03: Implement all strategies** `risk:high` `depends:[S01,S02]`
  > After this: Each of 7 strategies has real `evaluate()` logic grounded in prediction market research. `python3 -m analysis.backtest_strategies --strategy S1` runs for each SID and produces trades (or zero trades with explanation in metadata). Reports are generated in `reports/backtest/`.

- [ ] **S04: Operator playbook + verification** `risk:low` `depends:[S03]`
  > After this: `src/docs/STRATEGY_PLAYBOOK.md` exists with per-strategy CLI commands, metric definitions, profitability thresholds, and interpretation guide. Verification script passes all checks. User can copy-paste commands and understand results.

## Boundary Map

### S01

Produces:
- 7 strategy folders (`S1/` through `S7/`) each with `__init__.py`, `config.py` (with `get_default_config()` and `get_param_grid()`), `strategy.py` (with stub `evaluate()` returning None)
- Updated `TEMPLATE/` matching new strategy shape
- Registry discovers all 7 strategies by folder name

Consumes:
- `shared/strategies/base.py` — BaseStrategy, StrategyConfig, MarketSnapshot, Signal
- `shared/strategies/registry.py` — auto-discovery convention

### S02

Produces:
- `engine.py` updated: `calculate_pnl_hold()` and `calculate_pnl_exit()` use dynamic fee function
- `engine.py` updated: `make_trade()` accepts `slippage` parameter and adjusts entry price
- `backtest_strategies.py` updated: `--slippage` and `--fee-rate` CLI flags
- Dynamic fee function: `polymarket_fee(price, base_rate)` implementing `base_rate × min(price, 1 - price)`

Consumes:
- `analysis/backtest/engine.py` — existing PnL functions
- `analysis/backtest_strategies.py` — existing CLI argument parser

### S01 + S02 → S03

S03 Produces:
- 7 strategies with real `evaluate()` implementations:
  - S1: Calibration Mispricing — exploit systematic bias in 50/50 pricing
  - S2: Early Momentum — detect directional velocity in first 30-60 seconds
  - S3: Mean Reversion — fade early spikes after partial reversion
  - S4: Volatility Regime — enter contrarian only under specific vol conditions
  - S5: Time-Phase Entry — optimal entry timing based on market phase
  - S6: Streak/Sequence — exploit consecutive same-direction outcomes
  - S7: Composite Ensemble — enter only when 2+ strategies agree
- Each strategy's `get_param_grid()` returns meaningful parameter combinations

Consumes from S01:
- Strategy folder scaffolding, config stubs, registry discovery
Consumes from S02:
- Engine with dynamic fees + slippage (strategies can set `signal_data["entry_second"]` and trust the engine handles the rest)

### S03 → S04

S04 Produces:
- `src/docs/STRATEGY_PLAYBOOK.md` — operator guide with:
  - Per-strategy CLI commands
  - Expected output format and sample interpretation
  - Metric definitions (Sharpe, Sortino, profit factor, win rate, drawdown, etc.)
  - Go/no-go thresholds for deployment decisions
  - How to compare strategies using the ranking table
  - How to use the optimizer for parameter tuning
- `scripts/verify_strategies.py` — verification script covering all M003 deliverables

Consumes from S03:
- All 7 strategies with real implementations
- Actual backtest output format and metrics
