# M001: Unified Strategy Framework

**Vision:** One strategy definition consumed identically by backtesting and live trading — no divergence in logic, parameters, or time units.

## Success Criteria

- A strategy defined in `shared/strategies/S1/` produces identical signals when run through analysis (backtest) and trading (live) on the same price data
- New strategies can be created by copying `shared/strategies/TEMPLATE/` and immediately work in both contexts
- The seconds-vs-ticks bug is eliminated — all strategies operate on elapsed-seconds-indexed data
- Trading bot runs with shared strategies without regressions in executor/redeemer/balance

## Key Risks / Unknowns

- **Live tick → seconds normalization** — irregular tick arrival means the trading adapter must interpolate or snap to nearest second. If this is lossy or wrong, parity breaks.
- **Signal backward compatibility** — executor expects specific `signal_data` fields from the current Signal. The shared Signal must satisfy those.

## Proof Strategy

- Live tick normalization → retire in S03 by building the trading adapter and verifying it produces the same seconds-indexed data as the analysis adapter on identical input
- Signal compatibility → retire in S03 by confirming the executor accepts shared Signal objects without modification

## Verification Classes

- Contract verification: Python import checks, syntax validation, parity test script
- Integration verification: analysis backtest runner produces results; trading bot evaluates strategies and executor accepts signals
- Operational verification: none required (Docker deployment unchanged)
- UAT / human verification: user confirms new strategy creation flow feels right

## Milestone Definition of Done

This milestone is complete only when all are true:

- `shared/strategies/` contains base classes, registry, S1, S2, and TEMPLATE
- Analysis adapter runs strategies via shared code and produces backtest results
- Trading adapter runs strategies via shared code and produces Signal objects the executor accepts
- Parity test confirms identical signals on identical data
- Parameter optimization script can grid-search a strategy's config space
- `src/core/` has zero modifications
- Trading executor, redeemer, balance, DB tables have zero modifications

## Requirement Coverage

- Covers: R001, R002, R003, R004, R005, R006, R007, R008, R009, R010, R011, R012
- Partially covers: none
- Leaves for later: none
- Orphan risks: none

## Slices

- [x] **S01: Shared strategy framework + data model** `risk:high` `depends:[]`
  > After this: `shared/strategies/` exists with base classes (StrategyConfig, MarketSnapshot, Signal), a registry that discovers strategies by folder, and S1 (spike reversion) ported with config. Importable and unit-testable but not yet wired to analysis or trading.

- [x] **S02: Analysis adapter — backtest through shared strategies** `risk:medium` `depends:[S01]`
  > After this: `python -m analysis.backtest_strategies` loads strategies from the shared registry, runs them against historical data via MarketSnapshot, and produces backtest metrics using the existing engine.

- [x] **S03: Trading adapter — live signals through shared strategies** `risk:medium` `depends:[S01]`
  > After this: trading bot's main loop evaluates strategies from the shared registry, converting live ticks to MarketSnapshot, producing Signal objects the executor accepts. Bot runs without regressions.

- [x] **S04: Port S2 + parity verification** `risk:low` `depends:[S02,S03]`
  > After this: S2 (volatility) is ported. A parity test script feeds identical price data through both adapters and asserts identical signals. The seconds-vs-ticks bug is provably eliminated.

- [x] **S05: Strategy template + parameter optimization** `risk:low` `depends:[S04]`
  > After this: `shared/strategies/TEMPLATE/` contains a documented skeleton. `python -m analysis.optimize --strategy S1` grid-searches the config space and ranks parameter combinations.

## Boundary Map

### S01 → S02

Produces:
- `shared/strategies/base.py` → `StrategyConfig` (dataclass), `BaseStrategy` (abstract class with `evaluate(snapshot) -> Signal|None`), `MarketSnapshot` (seconds-indexed price array + metadata), `Signal` (direction, entry_price, strategy_id, metadata)
- `shared/strategies/registry.py` → `discover_strategies() -> dict[str, BaseStrategy]`, `get_strategy(id) -> BaseStrategy`
- `shared/strategies/S1/config.py` → S1 parameters as a StrategyConfig instance
- `shared/strategies/S1/strategy.py` → S1Strategy(BaseStrategy) with evaluate() implementation

Consumes:
- nothing (first slice)

### S01 → S03

Produces:
- Same as S01 → S02 (shared interfaces)
- `Signal` dataclass must include all fields `trading/executor.py` currently expects from `trading.strategies.Signal`

Consumes:
- nothing (first slice)

### S02 → S04

Produces:
- `analysis/backtest_strategies.py` → runner that loads shared strategies and produces results
- Proven pattern for converting historical data → MarketSnapshot

Consumes from S01:
- `shared/strategies/` base classes, registry, S1

### S03 → S04

Produces:
- Trading adapter function: `list[Tick]` → `MarketSnapshot`
- Proven pattern for live tick → MarketSnapshot conversion

Consumes from S01:
- `shared/strategies/` base classes, registry, S1

### S04 → S05

Produces:
- S2 strategy in `shared/strategies/S2/`
- `scripts/parity_test.py` — verifiable proof that both adapters produce identical signals
- Confidence that the framework is correct and complete

Consumes from S02, S03:
- Both adapters working and tested
