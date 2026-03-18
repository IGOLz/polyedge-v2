# M003: Research-Backed Strategy Overhaul

**Gathered:** 2026-03-18
**Status:** Ready for planning

## Project Description

Replace the disposable proof-of-concept strategies (S1 spike reversion, S2 volatility) with 5-7 research-backed strategies designed for Polymarket's 5-minute crypto up/down markets. Upgrade the backtest engine with realistic Polymarket dynamic fee modeling and configurable slippage. Produce a complete operator playbook for running, interpreting, and making deployment decisions from backtest output.

## Why This Milestone

M001 proved the framework works — same strategy definition in backtest and live. M002 added unified reporting. But the strategies themselves were disposable ports of old logic (D005 confirmed this). The user now wants to run real backtests on real data, interpret results, and decide what to deploy. That requires:
- Strategies grounded in prediction market research, not legacy ports
- Realistic fee modeling (Polymarket's dynamic fees, not a flat 2%)
- Slippage modeling so backtest results survive contact with real execution
- An operator guide for interpreting output and making go/no-go decisions

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run `cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1` for each of 5-7 strategies and get JSON + Markdown reports with realistic profitability metrics
- Run all strategies at once to compare ranking scores across the full strategy set
- Filter by asset (`--assets BTC,ETH`) or duration to test strategies on subsets
- Read the operator playbook to understand what each metric means, what thresholds indicate profitability, and how to decide what's worth deploying live
- Trust that reported PnL reflects real-world fees and execution slippage

### Entry point / environment

- Entry point: CLI via `python3 -m analysis.backtest_strategies`
- Environment: local dev with DB connection to TimescaleDB (historical tick data)
- Live dependencies involved: TimescaleDB with historical market data from core collector

## Completion Class

- Contract complete means: all strategies import, construct, and produce signals on synthetic data; engine fee/slippage functions are unit-testable
- Integration complete means: each strategy runs through the full backtest pipeline against real DB data and produces reports
- Operational complete means: operator playbook exists and accurately describes the output the user will see

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Each strategy individually produces a non-empty report when run against the database
- The dynamic fee model produces different fees for different entry prices (not flat)
- Slippage penalty visibly affects reported PnL (running with slippage=0 vs slippage=0.01 produces different results)
- The operator playbook commands actually work when copy-pasted into a terminal

## Risks and Unknowns

- **Dynamic fee formula accuracy** — Polymarket's exact fee formula for short-term crypto markets may have changed since research. The CLOB docs describe `baseRate × min(price, 1 - price) × size` but the base rate value isn't publicly documented with precision. We'll implement what's documented and make the base rate configurable.
- **Data sufficiency for streak strategy** — The streak/sequence strategy needs consecutive same-asset markets. If the DB doesn't have dense enough data for some assets, this strategy may produce too few trades to be statistically meaningful.
- **Strategy edge may not exist** — Some of these strategies may not be profitable even with perfect backtesting. That's expected and fine — the point is to give the user the tools to discover this, not to guarantee profitability.

## Existing Codebase / Prior Art

- `src/shared/strategies/base.py` — BaseStrategy, StrategyConfig, MarketSnapshot, Signal (the contract all strategies implement)
- `src/shared/strategies/registry.py` — Auto-discovery of strategy folders
- `src/shared/strategies/report.py` — StrategyReport for JSON/Markdown output
- `src/analysis/backtest_strategies.py` — CLI entry point, runs strategies through engine
- `src/analysis/backtest/engine.py` — Trade recording, PnL calculation, compute_metrics(), currently uses flat 2% fee
- `src/analysis/backtest/data_loader.py` — Loads markets + ticks from TimescaleDB
- `src/analysis/backtest/module_1_basic_entry.py` through `module_7_composite.py` — Old analysis modules (reference implementations, not part of shared strategy framework)
- `src/analysis/strategies/` — Old standalone strategy backtests (calibration, momentum, streak, farming)

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R014 — Self-contained strategy folders with config, evaluate(), param grid
- R015 — Old S1/S2 deleted, TEMPLATE updated
- R016 — Dynamic Polymarket fee model in engine
- R017 — Configurable slippage penalty
- R018 — Independent CLI execution per strategy
- R019 — Profitability metrics with go/no-go guidance
- R020 — Coverage of major viable strategy families
- R021 — Multi-asset support (BTC, ETH, XRP, SOL)
- R022 — Fee-aware profitability reporting

## Scope

### In Scope

- Delete old S1/S2 strategy folders
- Implement 5-7 new strategies in `shared/strategies/`
- Update TEMPLATE for new strategy shape
- Upgrade engine with dynamic Polymarket fee formula
- Add configurable slippage penalty to engine
- Operator playbook (Markdown) with per-strategy commands, metric interpretation, profitability thresholds
- Verification script covering imports, construction, backtest execution for all new strategies

### Out of Scope / Non-Goals

- Modifying `src/core/` in any way (R010)
- Modifying trading bot to use new strategies (user decides after seeing backtest results)
- Parameter optimization runs (the optimizer exists from M001; user runs it themselves)
- Live trading integration
- Cross-platform arbitrage (would need Kalshi/Binance data feeds)
- Order book depth strategies (would need order book data, not just up_price ticks)

## Technical Constraints

- Strategies must implement `BaseStrategy.evaluate(snapshot: MarketSnapshot) -> Signal | None` — pure, sync, no side effects
- Each strategy folder must have `strategy.py`, `config.py`, `__init__.py` matching registry discovery convention
- Engine fee/slippage changes must be backward-compatible (existing tests should not break)
- `src/core/` is read-only — never touch

## Integration Points

- `analysis/backtest/engine.py` — fee and slippage changes here affect all backtest results
- `analysis/backtest_strategies.py` — CLI entry point, already supports `--strategy SID`
- `shared/strategies/registry.py` — auto-discovers new strategies
- `analysis/optimize.py` — uses `get_param_grid()` from each strategy's config module

## Open Questions

- **Polymarket base fee rate** — Research found fees up to ~3.15% at 50/50 prices. The exact `baseRate` constant isn't precisely documented. Will implement the formula and make the rate configurable. Current thinking: use the documented CLOB formula with a conservative estimate, and let the user override via CLI flag.
- **Streak strategy data density** — Unknown how many consecutive same-asset markets exist in the DB. Will implement the strategy regardless and let the backtest reveal whether there's enough data. If total trades < 20, the playbook will flag it as statistically insignificant.
