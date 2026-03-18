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
- **Status:** validated
- **Why:** Strategies must be modular and independently testable; param grid enables optimization
- **Source:** user
- **Primary Owner:** M003/S01
- **Supporting Slices:** M003/S03
- **Validation:** M003
- **Notes:** All 7 strategies exist with config.py (get_default_config + get_param_grid) and strategy.py (evaluate() implementations). Verified by verify_m003_milestone.sh checks 2, 6, 7.

### R015: Old S1/S2 strategies are deleted; TEMPLATE is updated for new strategy shape

- **Class:** core-capability
- **Status:** validated
- **Why:** Clean slate — old strategies were disposable proof-of-concept tenants (D005)
- **Source:** user
- **Primary Owner:** M003/S01
- **Supporting Slices:** none
- **Validation:** M003
- **Notes:** verify_m003_milestone.sh check 1 proves old nested structure removed, new flat S1-S7 exist. TEMPLATE updated with get_param_grid().

### R016: Engine models Polymarket dynamic taker fees (not flat 2%) for short-term crypto markets

- **Class:** quality-attribute
- **Status:** validated
- **Why:** Flat 2% fee doesn't reflect real Polymarket fee structure; backtest profitability must be realistic
- **Source:** user
- **Primary Owner:** M003/S02
- **Supporting Slices:** none
- **Validation:** M003
- **Notes:** verify_m003_milestone.sh check 4 proves polymarket_dynamic_fee() produces different fees at different prices (0.63% at 0.10, 3.15% at 0.50, 0.63% at 0.90).

### R017: Engine applies configurable slippage penalty to entry prices

- **Class:** quality-attribute
- **Status:** validated
- **Why:** Backtests that ignore slippage overstate profitability; configurable penalty models realistic execution
- **Source:** user
- **Primary Owner:** M003/S02
- **Supporting Slices:** none
- **Validation:** M003
- **Notes:** verify_m003_milestone.sh check 5 proves slippage affects PnL (0.484250 → 0.474874 with slippage=0.01).

### R018: Each strategy is independently runnable via `--strategy SID` CLI flag

- **Class:** primary-user-loop
- **Status:** validated
- **Why:** User needs to evaluate each strategy individually before deciding what to deploy
- **Source:** user
- **Primary Owner:** M003/S03
- **Supporting Slices:** M003/S04
- **Validation:** M003
- **Notes:** verify_m003_milestone.sh check 6 proves S1 evaluates on synthetic data. All 7 strategies import (check 2). CLI --strategy flag verified (check 5).

### R019: Backtest output includes clear profitability metrics and go/no-go guidance per strategy

- **Class:** operability
- **Status:** validated
- **Why:** User needs to understand what metrics matter and what thresholds indicate real profitability
- **Source:** user
- **Primary Owner:** M003/S04
- **Supporting Slices:** none
- **Validation:** M003
- **Notes:** S04 delivered src/docs/STRATEGY_PLAYBOOK.md (1189 lines) with 18 metrics, formulas, thresholds, and 6-threshold Go/No-Go framework.

### R020: Strategies cover the major viable approaches for 5-min crypto up/down prediction markets

- **Class:** core-capability
- **Status:** validated
- **Why:** Comprehensive coverage maximizes chance of finding real edge; research identified 5-7 distinct families
- **Source:** inferred
- **Primary Owner:** M003/S03
- **Supporting Slices:** none
- **Validation:** M003
- **Notes:** S03 delivered 7 distinct strategy families (calibration, momentum, mean reversion, volatility regime, time-phase, streak, composite ensemble).

### R021: Strategies work across all collected assets (BTC, ETH, XRP, SOL)

- **Class:** core-capability
- **Status:** validated
- **Why:** Data is collected for all 5-minute market types; strategies should not be BTC-only
- **Source:** user
- **Primary Owner:** M003/S03
- **Supporting Slices:** none
- **Validation:** M003
- **Notes:** All strategies use MarketSnapshot which is asset-agnostic. Playbook documents --assets CLI flag for filtering.

### R022: Backtest considers Polymarket fee dynamics when reporting profitability

- **Class:** quality-attribute
- **Status:** validated
- **Why:** Profitability metrics must reflect what the trader actually keeps after fees
- **Source:** user
- **Primary Owner:** M003/S02
- **Supporting Slices:** M003/S04
- **Validation:** M003
- **Notes:** verify_m003_milestone.sh check 4 proves dynamic fees integrated. Playbook explains thresholds account for fees.

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
| R014 | core-capability | validated | M003/S01 | M003/S03 | M003 |
| R015 | core-capability | validated | M003/S01 | none | M003 |
| R016 | quality-attribute | validated | M003/S02 | none | M003 |
| R017 | quality-attribute | validated | M003/S02 | none | M003 |
| R018 | primary-user-loop | validated | M003/S03 | M003/S04 | M003 |
| R019 | operability | validated | M003/S04 | none | M003 |
| R020 | core-capability | validated | M003/S03 | none | M003 |
| R021 | core-capability | validated | M003/S03 | none | M003 |
| R022 | quality-attribute | validated | M003/S02 | M003/S04 | M003 |

## Coverage Summary

- Active requirements: 12
- Validated requirements: 9
- Mapped to slices: 21
- Unmapped active requirements: 0
