# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — Each strategy is defined once and consumed by both analysis and trading without duplication
- Class: core-capability
- Status: active
- Description: One config, one signal logic file per strategy — consumed identically by backtest and live trading
- Why it matters: Eliminates divergence between backtest and live behavior
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S02, M001/S03
- Validation: unmapped
- Notes: —

### R002 — Strategies live in `shared/strategies/S1/`, `S2/`, etc., folder-per-strategy
- Class: core-capability
- Status: active
- Description: Each strategy is a folder containing config and evaluate module, discovered automatically
- Why it matters: Consistent naming and discovery; adding a strategy means adding a folder
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M003/S01
- Validation: unmapped
- Notes: M003 replaces old S1/S2 with new research-backed strategies in the same folder structure

### R003 — MarketSnapshot with prices indexed by elapsed seconds
- Class: core-capability
- Status: active
- Description: Both analysis and trading produce a MarketSnapshot with prices indexed by elapsed seconds, eliminating the tick-count-as-time bug
- Why it matters: The concrete bug that motivated this work
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S02, M001/S03
- Validation: unmapped
- Notes: —

### R004 — Single Signal type used by both analysis and trading
- Class: core-capability
- Status: active
- Description: Signal type (direction, entry_price, strategy_id, metadata) used by both analysis results and trading execution
- Why it matters: Trading executor already consumes a Signal; analysis needs to produce the same shape
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R005 — Analysis converts historical DB data to MarketSnapshot and runs shared evaluate
- Class: primary-user-loop
- Status: active
- Description: Analysis converts historical DB data to MarketSnapshot, runs the shared strategy evaluate function, and collects results for backtesting
- Why it matters: Backtesting is how strategies are validated before going live
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: M003/S03
- Validation: unmapped
- Notes: —

### R006 — Trading converts live ticks to MarketSnapshot and runs shared evaluate
- Class: primary-user-loop
- Status: active
- Description: Trading converts live tick streams to MarketSnapshot, runs the shared strategy evaluate function, and produces Signal objects for the executor
- Why it matters: Live trading must use the exact same logic path as backtesting
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R007 — Signal parity between analysis and trading
- Class: quality-attribute
- Status: active
- Description: Same strategy config + same price data produces identical signals regardless of context
- Why it matters: The entire point — no more "works in backtest, different in prod"
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: none
- Validation: unmapped
- Notes: Verified by running both adapters on fixture data and comparing outputs

### R008 — Strategy auto-discovery registry
- Class: core-capability
- Status: active
- Description: Strategies are discovered and loaded by ID (S1, S2, ...) via a registry that scans `shared/strategies/`
- Why it matters: Adding a strategy is just adding a folder; no hardcoded imports elsewhere
- Source: inferred
- Primary owning slice: M001/S01
- Supporting slices: M003/S01
- Validation: unmapped
- Notes: —

### R009 — Executor, redeemer, balance, bot_trades DB tables remain unchanged
- Class: constraint
- Status: active
- Description: Only the strategy evaluation path is rewired; trading infra stays untouched
- Why it matters: Trading infra is proven and in production; minimizing blast radius
- Source: user
- Primary owning slice: —
- Supporting slices: M001/S03
- Validation: unmapped
- Notes: —

### R010 — `src/core/` is not modified in any way
- Class: constraint
- Status: active
- Description: Core runs 24/7 collecting data; it must never be disrupted
- Why it matters: Core runs 24/7 collecting data
- Source: user
- Primary owning slice: —
- Supporting slices: none
- Validation: unmapped
- Notes: —

### R011 — TEMPLATE folder with documented skeleton for new strategies
- Class: operability
- Status: active
- Description: A TEMPLATE folder in `shared/strategies/` with a documented skeleton that a developer copies to create a new strategy
- Why it matters: Lowers the bar for creating new strategies; enforces the interface contract
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: M003/S01
- Validation: unmapped
- Notes: M003 updates TEMPLATE to reflect new strategy shape (with param grid, slippage-aware evaluate)

### R012 — Grid-search optimization script
- Class: differentiator
- Status: active
- Description: An optimization script in analysis that grid-searches a strategy's config space and ranks parameter combinations by backtest performance
- Why it matters: Strategies have many tunable parameters; systematic search replaces manual tweaking
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: M001/S02
- Validation: unmapped
- Notes: —

### R034 — Each strategy's param grid produces 1M+ combinations via fine-grained value steps
- Class: core-capability
- Status: active
- Description: All 7 strategies declare fine-grained parameter ranges (e.g., 0.02 steps for prices, 5-10s steps for time windows) producing at least 1 million combinations per strategy
- Why it matters: Current 648-1728 combos barely scratch the surface; exhaustive exploration is needed to find profitable sweet spots
- Source: user
- Primary owning slice: M005/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Includes trailing SL parameters (trailing_sl bool + trail_distance float) in grids

### R035 — Optimizer uses multiprocessing to parallelize backtests across all CPU cores
- Class: core-capability
- Status: active
- Description: Grid search distributes parameter combinations across CPU cores using Python multiprocessing with shared market data
- Why it matters: Millions of combos on a single core would take days; parallelization makes it practical
- Source: user
- Primary owning slice: M005/S02
- Supporting slices: none
- Validation: unmapped
- Notes: Market data loaded once, shared across workers

### R036 — ROI metric with configurable bet size
- Class: primary-user-loop
- Status: active
- Description: ROI = total_pnl / (num_bets * bet_size), default bet_size=$10, configurable via --bet-size CLI flag
- Why it matters: Grounds profitability metrics in real dollar terms for trading decisions
- Source: user
- Primary owning slice: M005/S02
- Supporting slices: M005/S03
- Validation: unmapped
- Notes: —

### R037 — Rich post-optimization report with top 5 by score, PnL, and ROI
- Class: primary-user-loop
- Status: active
- Description: After optimization, generate a Markdown report per strategy showing top 5 overall (composite score), top 5 by PnL, top 5 by ROI, plus distribution stats
- Why it matters: Actionable output for deciding which config to deploy to live trading
- Source: user
- Primary owning slice: M005/S03
- Supporting slices: none
- Validation: unmapped
- Notes: Always show best available even if nothing is profitable

### R038 — Batched progress output during optimization
- Class: operability
- Status: active
- Description: Progress output shows batched combo counter (every Nth combination), not full config dump per line
- Why it matters: Current output prints full config for every combo, which is noisy and slows down runs
- Source: user
- Primary owning slice: M005/S02
- Supporting slices: none
- Validation: unmapped
- Notes: Print interval auto-adjusts based on total combos

### R039 — ASCII-safe print/log output for Windows compatibility
- Class: operability
- Status: active
- Description: All Python print and log statements use ASCII-safe characters — no arrows, checkmarks, crosses, or other non-cp1252 Unicode
- Why it matters: Windows default encoding (cp1252) cannot render these characters, causing crashes
- Source: user
- Primary owning slice: M005/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Affects backtest_strategies.py, trading/main.py, shared/strategies/report.py, and others

### R040 — CLI documentation with all optimizer flags and examples
- Class: operability
- Status: active
- Description: Comprehensive documentation covering all optimizer CLI flags, example commands, how to read reports, and strategy parameter reference
- Why it matters: Users need a single reference for running optimizations and interpreting results
- Source: user
- Primary owning slice: M005/S03
- Supporting slices: none
- Validation: unmapped
- Notes: Written in src/docs/ or README section

### R041 — Metrics-only storage at million-combo scale
- Class: constraint
- Status: active
- Description: No per-config trade logs saved — only aggregated metrics CSV for all combos
- Why it matters: Saving trade logs for millions of configs would produce terabytes of data
- Source: inferred
- Primary owning slice: M005/S02
- Supporting slices: none
- Validation: unmapped
- Notes: Trade logs from save_module_results removed; metrics CSV remains

### R042 — Trailing stop loss as opt-in parameter with configurable trail distance
- Class: core-capability
- Status: active
- Description: trailing_sl (bool) enables trailing stop; trail_distance (float) controls how far behind best price the SL follows. Both are grid-searchable parameters. When disabled, fixed SL behavior is unchanged.
- Why it matters: Trailing SL locks in profits as trades move favorably — a standard risk management technique
- Source: user
- Primary owning slice: M005/S02
- Supporting slices: M005/S01
- Validation: unmapped
- Notes: Promotes former R032 (deferred). Fixed trail distance behind best-seen price. Direction-aware (Up: trail below peak, Down: trail above trough).

## Validated

### R014 — Each strategy is a self-contained folder with config, evaluate(), and param grid
- Class: core-capability
- Status: validated
- Description: All 7 strategies exist with config.py (get_default_config + get_param_grid) and strategy.py (evaluate() implementations)
- Why it matters: Strategies must be modular and independently testable
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: M003/S03
- Validation: M003
- Notes: Verified by verify_m003_milestone.sh checks 2, 6, 7

### R015 — Old S1/S2 strategies deleted; TEMPLATE updated for new strategy shape
- Class: core-capability
- Status: validated
- Description: Clean slate — old strategies removed, new flat S1-S7 exist
- Why it matters: Old strategies were disposable proof-of-concept tenants
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: none
- Validation: M003
- Notes: verify_m003_milestone.sh check 1

### R016 — Engine models Polymarket dynamic taker fees
- Class: quality-attribute
- Status: validated
- Description: Dynamic fee formula `base_rate * min(price, 1-price)` replaces flat 2%
- Why it matters: Flat 2% fee doesn't reflect real Polymarket fee structure
- Source: user
- Primary owning slice: M003/S02
- Supporting slices: none
- Validation: M003
- Notes: verify_m003_milestone.sh check 4

### R017 — Engine applies configurable slippage penalty
- Class: quality-attribute
- Status: validated
- Description: Configurable slippage penalty adjusts entry prices
- Why it matters: Backtests that ignore slippage overstate profitability
- Source: user
- Primary owning slice: M003/S02
- Supporting slices: none
- Validation: M003
- Notes: verify_m003_milestone.sh check 5

### R018 — Each strategy independently runnable via --strategy SID
- Class: primary-user-loop
- Status: validated
- Description: CLI --strategy flag runs a single strategy
- Why it matters: User needs to evaluate each strategy individually
- Source: user
- Primary owning slice: M003/S03
- Supporting slices: M003/S04
- Validation: M003
- Notes: verify_m003_milestone.sh check 6

### R019 — Backtest output includes profitability metrics and go/no-go guidance
- Class: operability
- Status: validated
- Description: Strategy playbook with 18 metrics, formulas, thresholds, and 6-threshold Go/No-Go framework
- Why it matters: User needs to understand what metrics matter and what thresholds indicate profitability
- Source: user
- Primary owning slice: M003/S04
- Supporting slices: none
- Validation: M003
- Notes: S04 delivered STRATEGY_PLAYBOOK.md (1189 lines)

### R020 — Strategies cover major viable approaches for 5-min crypto up/down markets
- Class: core-capability
- Status: validated
- Description: 7 distinct strategy families (calibration, momentum, mean reversion, volatility regime, time-phase, streak, composite ensemble)
- Why it matters: Comprehensive coverage maximizes chance of finding real edge
- Source: inferred
- Primary owning slice: M003/S03
- Supporting slices: none
- Validation: M003
- Notes: —

### R021 — Strategies work across all collected assets (BTC, ETH, XRP, SOL)
- Class: core-capability
- Status: validated
- Description: All strategies use asset-agnostic MarketSnapshot
- Why it matters: Data is collected for all 5-minute market types
- Source: user
- Primary owning slice: M003/S03
- Supporting slices: none
- Validation: M003
- Notes: —

### R022 — Backtest considers Polymarket fee dynamics when reporting profitability
- Class: quality-attribute
- Status: validated
- Description: Dynamic fees integrated into PnL calculations
- Why it matters: Profitability metrics must reflect what the trader actually keeps after fees
- Source: user
- Primary owning slice: M003/S02
- Supporting slices: M003/S04
- Validation: M003
- Notes: —

### R023 — All strategies declare stop_loss and take_profit parameter ranges in config grids
- Class: core-capability
- Status: validated
- Description: All 7 strategies have get_param_grid() returning dicts with stop_loss and take_profit keys
- Why it matters: Grid search must explore SL/TP combinations systematically
- Source: user
- Primary owning slice: M004/S01
- Supporting slices: none
- Validation: M004
- Notes: S05 verified via verify_m004_milestone.sh check 1

### R024 — TEMPLATE demonstrates stop_loss and take_profit pattern
- Class: core-capability
- Status: validated
- Description: TEMPLATE/config.py has working get_param_grid() with SL/TP keys and comments explaining absolute price thresholds
- Why it matters: Future strategy authors need clear example of SL/TP semantics
- Source: user
- Primary owning slice: M004/S01
- Supporting slices: M004/S02
- Validation: M004
- Notes: —

### R025 — Engine simulates stop loss and take profit exits by tracking price every second
- Class: core-capability
- Status: validated
- Description: simulate_sl_tp_exit() scans prices second-by-second with direction-specific thresholds
- Why it matters: Backtest must model early exits accurately
- Source: user
- Primary owning slice: M004/S02
- Supporting slices: M004/S03, M004/S04
- Validation: M004/S02
- Notes: 13 unit tests covering Up/Down x SL/TP/resolution matrix

### R026 — Grid search generates Cartesian product including SL/TP dimensions
- Class: primary-user-loop
- Status: validated
- Description: optimize.py introspects config dataclass to split params and thread exit_params through
- Why it matters: User needs to explore full parameter space including exit thresholds
- Source: user
- Primary owning slice: M004/S03
- Supporting slices: none
- Validation: M004/S03
- Notes: —

### R027 — Backtest output CSV includes stop_loss, take_profit columns
- Class: operability
- Status: validated
- Description: Results CSV contains per-configuration SL/TP values
- Why it matters: User needs to see which SL/TP values each ranked combination used
- Source: user
- Primary owning slice: M004/S04
- Supporting slices: none
- Validation: M004/S04
- Notes: —

### R028 — Top 10 summary prints explicit SL/TP values
- Class: operability
- Status: validated
- Description: Console top 10 output displays SL/TP per ranked combination
- Why it matters: Quick access to best parameter sets without parsing full CSV
- Source: user
- Primary owning slice: M004/S04
- Supporting slices: none
- Validation: M004/S04
- Notes: —

### R029 — Strategy-specific SL/TP ranges tuned to typical entry prices
- Class: core-capability
- Status: validated
- Description: S1-S7 have customized SL/TP ranges per D013
- Why it matters: Generic ranges waste parameter space
- Source: inferred
- Primary owning slice: M004/S01
- Supporting slices: none
- Validation: M004
- Notes: —

### R030 — TEMPLATE provides clear example with documented absolute price threshold semantics
- Class: operability
- Status: validated
- Description: TEMPLATE/config.py explains absolute price semantics and direction-handling logic
- Why it matters: Future strategy authors must understand SL/TP are absolute prices
- Source: inferred
- Primary owning slice: M004/S01
- Supporting slices: none
- Validation: M004
- Notes: —

### R031 — Trades distinguish SL exit vs TP exit vs hold-to-resolution
- Class: operability
- Status: validated
- Description: Trade dataclass has exit_reason field ('sl', 'tp', 'resolution')
- Why it matters: User needs to understand which trades exited early and why
- Source: inferred
- Primary owning slice: M004/S04
- Supporting slices: M004/S02
- Validation: M004/S02
- Notes: —

## Deferred

*(No deferred requirements — R032 promoted to R042 active)*

## Out of Scope

### R013 — Old strategy parameters ported as-is (superseded by M003)
- Class: constraint
- Status: out-of-scope
- Description: Original disposable strategies replaced by M003's research-backed strategies
- Why it matters: Prevents scope creep
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Superseded by M003

### R033 — Live trading bot integration of SL/TP (backtest-only scope)
- Class: constraint
- Status: out-of-scope
- Description: SL/TP is backtest analysis only; live trading integration is a future milestone
- Why it matters: Milestone scope boundary
- Source: inferred
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: —

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
| R023 | core-capability | validated | M004/S01 | none | M004 |
| R024 | core-capability | validated | M004/S01 | M004/S02 | M004 |
| R025 | core-capability | validated | M004/S02 | M004/S03, M004/S04 | M004/S02 |
| R026 | primary-user-loop | validated | M004/S03 | none | M004/S03 |
| R027 | operability | validated | M004/S04 | none | M004/S04 |
| R028 | operability | validated | M004/S04 | none | M004/S04 |
| R029 | core-capability | validated | M004/S01 | none | M004 |
| R030 | operability | validated | M004/S01 | none | M004 |
| R031 | operability | validated | M004/S04 | M004/S02 | M004/S02 |
| R033 | constraint | out-of-scope | none | none | n/a |
| R034 | core-capability | active | M005/S01 | none | unmapped |
| R035 | core-capability | active | M005/S02 | none | unmapped |
| R036 | primary-user-loop | active | M005/S02 | M005/S03 | unmapped |
| R037 | primary-user-loop | active | M005/S03 | none | unmapped |
| R038 | operability | active | M005/S02 | none | unmapped |
| R039 | operability | active | M005/S01 | none | unmapped |
| R040 | operability | active | M005/S03 | none | unmapped |
| R041 | constraint | active | M005/S02 | none | unmapped |
| R042 | core-capability | active | M005/S02 | M005/S01 | unmapped |

## Coverage Summary

- Active requirements: 21
- Validated requirements: 18
- Deferred requirements: 0
- Out of scope: 2
- Total requirements: 41
- Mapped to slices: 39
- With proof: 25
- Unmapped active requirements: 12
