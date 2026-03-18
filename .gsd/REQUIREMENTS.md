# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — Unified strategy definition
- Class: core-capability
- Status: active
- Description: Each strategy is defined once — one config, one signal logic file — and consumed by both analysis and trading without duplication
- Why it matters: Eliminates divergence between backtest and live behavior; a strategy that backtests well will behave identically in production
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S02, M001/S03
- Validation: unmapped
- Notes: —

### R002 — Strategy folder structure (S1, S2, ...)
- Class: core-capability
- Status: active
- Description: Strategies live in `shared/strategies/S1/`, `S2/`, etc., each containing a config and evaluate module
- Why it matters: Consistent naming and discovery; adding a strategy means adding a folder
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R003 — Normalized market snapshot (seconds-indexed)
- Class: core-capability
- Status: active
- Description: Both analysis and trading produce a MarketSnapshot with prices indexed by elapsed seconds, eliminating the tick-count-as-time bug
- Why it matters: The concrete bug that motivated this work — trading used tick indices as seconds, analysis used proper seconds; they must match
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S02, M001/S03
- Validation: unmapped
- Notes: —

### R004 — Shared Signal dataclass
- Class: core-capability
- Status: active
- Description: A single Signal type (direction, entry_price, strategy_id, metadata) used by both analysis results and trading execution
- Why it matters: Trading executor already consumes a Signal; analysis needs to produce the same shape for parity verification
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R005 — Analysis adapter
- Class: primary-user-loop
- Status: active
- Description: Analysis converts historical DB data to MarketSnapshot, runs the shared strategy evaluate function, and collects results for backtesting
- Why it matters: Backtesting is how strategies are validated before going live
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R006 — Trading adapter
- Class: primary-user-loop
- Status: active
- Description: Trading converts live tick streams to MarketSnapshot, runs the shared strategy evaluate function, and produces Signal objects for the executor
- Why it matters: Live trading must use the exact same logic path as backtesting
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R007 — Identical behavior guarantee
- Class: quality-attribute
- Status: active
- Description: Same strategy config + same price data produces identical signals regardless of whether analysis or trading is running it
- Why it matters: The entire point — no more "works in backtest, different in prod"
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: none
- Validation: unmapped
- Notes: Verified by running both adapters on fixture data and comparing outputs

### R008 — Strategy registry
- Class: core-capability
- Status: active
- Description: Strategies are discovered and loaded by ID (S1, S2, ...) via a registry that scans `shared/strategies/`
- Why it matters: Adding a strategy is just adding a folder; no hardcoded imports elsewhere
- Source: inferred
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R009 — Trading infrastructure untouched
- Class: constraint
- Status: active
- Description: Executor, redeemer, balance, bot_trades DB tables remain unchanged; only the strategy evaluation path is rewired
- Why it matters: Trading infra is proven and in production; minimizing blast radius
- Source: user
- Primary owning slice: —
- Supporting slices: M001/S03
- Validation: unmapped
- Notes: —

### R010 — Core service untouched
- Class: constraint
- Status: active
- Description: `src/core/` is not modified in any way
- Why it matters: Core runs 24/7 collecting data; it must never be disrupted
- Source: user
- Primary owning slice: —
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R011 — Strategy authoring template
- Class: operability
- Status: active
- Description: A TEMPLATE folder in `shared/strategies/` with a documented skeleton that a developer copies to create a new strategy
- Why it matters: Lowers the bar for creating new strategies; enforces the interface contract
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R012 — Strategy parameter optimization
- Class: differentiator
- Status: active
- Description: An optimization script in analysis that grid-searches a strategy's config space and ranks parameter combinations by backtest performance
- Why it matters: Strategies have many tunable parameters; systematic search replaces manual tweaking
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: M001/S02
- Validation: unmapped
- Notes: —

## Validated

(none yet)

## Deferred

(none)

## Out of Scope

### R013 — Rewriting specific strategy logic
- Class: constraint
- Status: out-of-scope
- Description: The actual M3/M4/momentum/etc. strategy parameters and logic will be rewritten in the future; this milestone only ports them as-is to prove the framework
- Why it matters: Prevents scope creep — we're building the framework, not optimizing strategies
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Strategies ported are disposable first tenants of the new framework

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | active | M001/S01 | M001/S02, M001/S03 | unmapped |
| R002 | core-capability | active | M001/S01 | none | unmapped |
| R003 | core-capability | active | M001/S01 | M001/S02, M001/S03 | unmapped |
| R004 | core-capability | active | M001/S01 | none | unmapped |
| R005 | primary-user-loop | active | M001/S02 | none | unmapped |
| R006 | primary-user-loop | active | M001/S03 | none | unmapped |
| R007 | quality-attribute | active | M001/S04 | none | unmapped |
| R008 | core-capability | active | M001/S01 | none | unmapped |
| R009 | constraint | active | — | M001/S03 | unmapped |
| R010 | constraint | active | — | none | unmapped |
| R011 | operability | active | M001/S05 | none | unmapped |
| R012 | differentiator | active | M001/S05 | M001/S02 | unmapped |
| R013 | constraint | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 12
- Mapped to slices: 10
- Validated: 0
- Unmapped active requirements: 2 (R009, R010 are constraints verified by not touching those modules)
