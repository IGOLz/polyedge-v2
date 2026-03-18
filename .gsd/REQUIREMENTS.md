# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001: Each strategy is defined once — one config, one signal logic file — and consumed by both analysis and trading without duplication

- **Class:** core-capability
- **Status:** active
- **Why:** Eliminates divergence between backtest and live behavior; a strategy that backtests well will behave identically in production
- **Source:** user
- **Primary Owner:** M001/S01
- **Supporting Slices:** M001/S02, M001/S03
- **Validation:** unmapped
- **Notes:** —

### R002: Strategies live in `shared/strategies/S1/`, `S2/`, etc., each containing a config and evaluate module

- **Class:** core-capability
- **Status:** active
- **Why:** Consistent naming and discovery; adding a strategy means adding a folder
- **Source:** user
- **Primary Owner:** M001/S01
- **Supporting Slices:** M003/S01
- **Validation:** unmapped
- **Notes:** M003 replaces old S1/S2 with new research-backed strategies in the same folder structure

### R003: Both analysis and trading produce a MarketSnapshot with prices indexed by elapsed seconds, eliminating the tick-count-as-time bug

- **Class:** core-capability
- **Status:** active
- **Why:** The concrete bug that motivated this work — trading used tick indices as seconds, analysis used proper seconds; they must match
- **Source:** user
- **Primary Owner:** M001/S01
- **Supporting Slices:** M001/S02, M001/S03
- **Validation:** unmapped
- **Notes:** —

### R004: A single Signal type (direction, entry_price, strategy_id, metadata) used by both analysis results and trading execution

- **Class:** core-capability
- **Status:** active
- **Why:** Trading executor already consumes a Signal; analysis needs to produce the same shape for parity verification
- **Source:** user
- **Primary Owner:** M001/S01
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** —

### R005: Analysis converts historical DB data to MarketSnapshot, runs the shared strategy evaluate function, and collects results for backtesting

- **Class:** primary-user-loop
- **Status:** active
- **Why:** Backtesting is how strategies are validated before going live
- **Source:** user
- **Primary Owner:** M001/S02
- **Supporting Slices:** M003/S03
- **Validation:** unmapped
- **Notes:** —

### R006: Trading converts live tick streams to MarketSnapshot, runs the shared strategy evaluate function, and produces Signal objects for the executor

- **Class:** primary-user-loop
- **Status:** active
- **Why:** Live trading must use the exact same logic path as backtesting
- **Source:** user
- **Primary Owner:** M001/S03
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** —

### R007: Same strategy config + same price data produces identical signals regardless of whether analysis or trading is running it

- **Class:** quality-attribute
- **Status:** active
- **Why:** The entire point — no more "works in backtest, different in prod"
- **Source:** user
- **Primary Owner:** M001/S04
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** Verified by running both adapters on fixture data and comparing outputs

### R008: Strategies are discovered and loaded by ID (S1, S2, ...) via a registry that scans `shared/strategies/`

- **Class:** core-capability
- **Status:** active
- **Why:** Adding a strategy is just adding a folder; no hardcoded imports elsewhere
- **Source:** inferred
- **Primary Owner:** M001/S01
- **Supporting Slices:** M003/S01
- **Validation:** unmapped
- **Notes:** —

### R009: Executor, redeemer, balance, bot_trades DB tables remain unchanged; only the strategy evaluation path is rewired

- **Class:** constraint
- **Status:** active
- **Why:** Trading infra is proven and in production; minimizing blast radius
- **Source:** user
- **Primary Owner:** —
- **Supporting Slices:** M001/S03
- **Validation:** unmapped
- **Notes:** —

### R010: `src/core/` is not modified in any way

- **Class:** constraint
- **Status:** active
- **Why:** Core runs 24/7 collecting data; it must never be disrupted
- **Source:** user
- **Primary Owner:** —
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** —

### R011: A TEMPLATE folder in `shared/strategies/` with a documented skeleton that a developer copies to create a new strategy

- **Class:** operability
- **Status:** active
- **Why:** Lowers the bar for creating new strategies; enforces the interface contract
- **Source:** user
- **Primary Owner:** M001/S05
- **Supporting Slices:** M003/S01
- **Validation:** unmapped
- **Notes:** M003 updates TEMPLATE to reflect new strategy shape (with param grid, slippage-aware evaluate)

### R012: An optimization script in analysis that grid-searches a strategy's config space and ranks parameter combinations by backtest performance

- **Class:** differentiator
- **Status:** active
- **Why:** Strategies have many tunable parameters; systematic search replaces manual tweaking
- **Source:** user
- **Primary Owner:** M001/S05
- **Supporting Slices:** M001/S02
- **Validation:** unmapped
- **Notes:** —

### R014: Each strategy is a self-contained folder in `shared/strategies/` with config, evaluate(), and param grid

- **Class:** core-capability
- **Status:** active
- **Why:** Strategies must be modular and independently testable; param grid enables optimization
- **Source:** user
- **Primary Owner:** M003/S01
- **Supporting Slices:** M003/S03
- **Validation:** unmapped
- **Notes:** —

### R015: Old S1/S2 strategies are deleted; TEMPLATE is updated for new strategy shape

- **Class:** core-capability
- **Status:** active
- **Why:** Clean slate — old strategies were disposable proof-of-concept tenants (D005)
- **Source:** user
- **Primary Owner:** M003/S01
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** —

### R016: Engine models Polymarket dynamic taker fees (not flat 2%) for short-term crypto markets

- **Class:** quality-attribute
- **Status:** active
- **Why:** Flat 2% fee doesn't reflect real Polymarket fee structure; backtest profitability must be realistic
- **Source:** user
- **Primary Owner:** M003/S02
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** Dynamic fee formula: `baseRate × min(price, 1 - price) × size`, peaking at ~3.15% near 50-cent contracts

### R017: Engine applies configurable slippage penalty to entry prices

- **Class:** quality-attribute
- **Status:** active
- **Why:** Backtests that ignore slippage overstate profitability; configurable penalty models realistic execution
- **Source:** user
- **Primary Owner:** M003/S02
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** Default ~1 cent penalty, configurable per-run

### R018: Each strategy is independently runnable via `--strategy SID` CLI flag

- **Class:** primary-user-loop
- **Status:** active
- **Why:** User needs to evaluate each strategy individually before deciding what to deploy
- **Source:** user
- **Primary Owner:** M003/S03
- **Supporting Slices:** M003/S04
- **Validation:** unmapped
- **Notes:** Already supported by `backtest_strategies.py --strategy` flag; just needs new strategies registered

### R019: Backtest output includes clear profitability metrics and go/no-go guidance per strategy

- **Class:** operability
- **Status:** active
- **Why:** User needs to understand what metrics matter and what thresholds indicate real profitability
- **Source:** user
- **Primary Owner:** M003/S04
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** Operator playbook with metric interpretation guide

### R020: Strategies cover the major viable approaches for 5-min crypto up/down prediction markets

- **Class:** core-capability
- **Status:** active
- **Why:** Comprehensive coverage maximizes chance of finding real edge; research identified 5-7 distinct families
- **Source:** inferred
- **Primary Owner:** M003/S03
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** Calibration, momentum, mean reversion, volatility regime, time-phase, streak, composite ensemble

### R021: Strategies work across all collected assets (BTC, ETH, XRP, SOL)

- **Class:** core-capability
- **Status:** active
- **Why:** Data is collected for all 5-minute market types; strategies should not be BTC-only
- **Source:** user
- **Primary Owner:** M003/S03
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** Strategies use MarketSnapshot which is asset-agnostic; asset filtering via CLI `--assets` flag

### R022: Backtest considers Polymarket fee dynamics when reporting profitability

- **Class:** quality-attribute
- **Status:** active
- **Why:** Profitability metrics must reflect what the trader actually keeps after fees
- **Source:** user
- **Primary Owner:** M003/S02
- **Supporting Slices:** M003/S04
- **Validation:** unmapped
- **Notes:** Reports should show pre-fee and post-fee metrics or at minimum use realistic fees

## Out of Scope

### R013: The actual M3/M4/momentum/etc. strategy parameters and logic will be rewritten in the future; this milestone only ports them as-is to prove the framework

- **Class:** constraint
- **Status:** out-of-scope
- **Why:** Prevents scope creep — we're building the framework, not optimizing strategies
- **Source:** user
- **Primary Owner:** none
- **Supporting Slices:** none
- **Validation:** n/a
- **Notes:** Strategies ported are disposable first tenants of the new framework. Superseded by M003 which replaces them with real strategies.

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | active | M001/S01 | M001/S02, M001/S03 | unmapped |
| R002 | core-capability | active | M001/S01 | M003/S01 | unmapped |
| R003 | core-capability | active | M001/S01 | M001/S02, M001/S03 | unmapped |
| R004 | core-capability | active | M001/S01 | none | unmapped |
| R005 | primary-user-loop | active | M001/S02 | M003/S03 | unmapped |
| R006 | primary-user-loop | active | M001/S03 | none | unmapped |
| R007 | quality-attribute | active | M001/S04 | none | unmapped |
| R008 | core-capability | active | M001/S01 | M003/S01 | unmapped |
| R009 | constraint | active | — | M001/S03 | unmapped |
| R010 | constraint | active | — | none | unmapped |
| R011 | operability | active | M001/S05 | M003/S01 | unmapped |
| R012 | differentiator | active | M001/S05 | M001/S02 | unmapped |
| R013 | constraint | out-of-scope | none | none | n/a |
| R014 | core-capability | active | M003/S01 | M003/S03 | unmapped |
| R015 | core-capability | active | M003/S01 | none | unmapped |
| R016 | quality-attribute | active | M003/S02 | none | unmapped |
| R017 | quality-attribute | active | M003/S02 | none | unmapped |
| R018 | primary-user-loop | active | M003/S03 | M003/S04 | unmapped |
| R019 | operability | active | M003/S04 | none | unmapped |
| R020 | core-capability | active | M003/S03 | none | unmapped |
| R021 | core-capability | active | M003/S03 | none | unmapped |
| R022 | quality-attribute | active | M003/S02 | M003/S04 | unmapped |

## Coverage Summary

- Active requirements: 21
- Mapped to slices: 21
- Validated: 0
- Unmapped active requirements: 0
