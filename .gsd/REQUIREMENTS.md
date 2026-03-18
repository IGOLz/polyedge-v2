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

### R023: All strategies declare stop_loss and take_profit parameter ranges in their config grids

- **Class:** core-capability
- **Status:** validated
- **Why:** Grid search must explore SL/TP combinations systematically; strategies declare their viable exit parameter ranges
- **Source:** user
- **Primary Owner:** M004/S01
- **Supporting Slices:** none
- **Validation:** M004
- **Notes:** S01 delivered: all 7 strategies (S1-S7) have get_param_grid() returning dicts with stop_loss and take_profit keys, each with 3 values. Grid sizes range 648-1728 combinations per strategy. S05 verified end-to-end integration via verify_m004_milestone.sh check 1.

### R024: TEMPLATE demonstrates stop_loss and take_profit pattern with documented semantics

- **Class:** core-capability
- **Status:** validated
- **Why:** Future strategy authors need clear example of how to declare SL/TP parameters and understand absolute price threshold semantics
- **Source:** user
- **Primary Owner:** M004/S01
- **Supporting Slices:** M004/S02
- **Validation:** M004
- **Notes:** S01 delivered: TEMPLATE/config.py has working get_param_grid() with SL/TP keys and comments explaining absolute price thresholds and direction handling. TEMPLATE is now executable (returns real dict, not empty). S05 verified TEMPLATE imports without errors and includes SL/TP parameters via verify_m004_milestone.sh check 7.

### R025: Engine simulates stop loss and take profit exits by tracking price every second

- **Class:** core-capability
- **Status:** validated
- **Why:** Backtest must model early exits accurately; holding to resolution overstates profitability
- **Source:** user
- **Primary Owner:** M004/S02
- **Supporting Slices:** M004/S03, M004/S04
- **Validation:** M004/S02
- **Notes:** S02 delivered: simulate_sl_tp_exit() scans prices array second-by-second after entry, checks SL/TP thresholds with direction-specific logic (Up: SL when price ≤ stop_loss, TP when price ≥ take_profit; Down: inverted thresholds per D012), handles NaN prices, returns (exit_second, exit_price, exit_reason). Integrated with make_trade() to accept optional stop_loss and take_profit parameters. Verified by 13 unit tests covering Up/Down × SL/TP/resolution matrix, NaN handling, edge cases, and PnL correctness.

### R026: Grid search generates Cartesian product including SL/TP dimensions

- **Class:** primary-user-loop
- **Status:** validated
- **Why:** User needs to explore full parameter space including exit thresholds
- **Source:** user
- **Primary Owner:** M004/S03
- **Supporting Slices:** none
- **Validation:** M004/S03
- **Notes:** S03 delivered: optimize.py introspects config dataclass to split param_dict into strategy_params (config fields) and exit_params (stop_loss, take_profit), threads exit_params through run_strategy() to make_trade(), and augments metrics dict with SL/TP values. Verified by dry-run showing 972 combinations for S1 with SL/TP dimensions, and results CSV containing stop_loss and take_profit columns with correct per-combination values.

### R027: Backtest output CSV includes stop_loss, take_profit, and exit_reason columns

- **Class:** operability
- **Status:** validated
- **Why:** User needs to see which SL/TP values each ranked combination used
- **Source:** user
- **Primary Owner:** M004/S04
- **Supporting Slices:** none
- **Validation:** M004/S04
- **Notes:** S04 delivered: Results CSV contains stop_loss and take_profit columns with per-configuration values. Note: exit_reason field exists on individual Trade objects (validated in S02), but aggregated metrics CSVs don't contain per-trade fields. This is correct by design—metrics summarize outcomes across trades.

### R028: Top 10 summary prints explicit SL/TP values for each ranked combination

- **Class:** operability
- **Status:** validated
- **Why:** User needs quick access to best parameter sets without parsing full CSV
- **Source:** user
- **Primary Owner:** M004/S04
- **Supporting Slices:** none
- **Validation:** M004/S04
- **Notes:** S04 delivered: optimize.py top 10 console output enhanced to display stop_loss and take_profit values alongside existing metrics (Bets, WR, PnL, Sharpe, Score). Format: `SL=0.40, TP=0.75` per ranked combination. Verified by grep pattern match on console output.

### R029: Strategy-specific SL/TP ranges are tuned to each strategy's typical entry prices

- **Class:** core-capability
- **Status:** validated
- **Why:** Generic ranges waste parameter space; strategy-aware ranges improve search efficiency
- **Source:** inferred
- **Primary Owner:** M004/S01
- **Supporting Slices:** none
- **Validation:** M004
- **Notes:** S01 delivered: S1-S7 have customized SL/TP ranges per decision D013. Examples: S1 entry 0.45-0.55 → SL [0.35,0.40,0.45], TP [0.65,0.70,0.75]; S3 spike-based → SL [0.15,0.20,0.25], TP [0.75,0.80,0.85]. S05 verified end-to-end via verify_m004_milestone.sh check 4 proving CSV has SL/TP values in expected ranges.

### R030: TEMPLATE provides clear example with documented absolute price threshold semantics

- **Class:** operability
- **Status:** validated
- **Why:** Future strategy authors must understand that SL/TP are absolute prices, not percentages, and that engine handles direction swapping
- **Source:** inferred
- **Primary Owner:** M004/S01
- **Supporting Slices:** none
- **Validation:** M004
- **Notes:** S01 delivered: TEMPLATE/config.py has comments explaining absolute price semantics and direction-handling logic. Example shows stop_loss: [0.35, 0.40, 0.45] with clear explanation that engine swaps for Down bets. S05 verified TEMPLATE imports and includes SL/TP parameters via verify_m004_milestone.sh check 7.

### R031: Trades distinguish SL exit vs TP exit vs hold-to-resolution in output

- **Class:** operability
- **Status:** validated
- **Why:** User needs to understand which trades exited early and why
- **Source:** inferred
- **Primary Owner:** M004/S04
- **Supporting Slices:** M004/S02
- **Validation:** M004/S02
- **Notes:** S02 delivered: Trade dataclass extended with exit_reason field (defaults to 'resolution' for backward compatibility). Three semantic values: 'sl' (stop loss hit), 'tp' (take profit hit), 'resolution' (held to market close). Field is populated by simulate_sl_tp_exit() and included in CSV output via save_trade_log(). Verified by unit tests showing correct exit_reason for all exit paths.

## Deferred

### R032: Trailing stop loss (dynamic SL that moves with profit)

- **Class:** quality-attribute
- **Status:** deferred
- **Why:** More sophisticated exit logic; defer until fixed SL/TP proves useful
- **Source:** research
- **Primary Owner:** none
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** May be valuable for momentum strategies; revisit after M004 results

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

### R033: Live trading bot integration of SL/TP (this milestone is backtest-only)

- **Class:** constraint
- **Status:** out-of-scope
- **Why:** Milestone scope is backtest analysis only; live trading integration is a future milestone
- **Source:** inferred
- **Primary Owner:** none
- **Supporting Slices:** none
- **Validation:** n/a
- **Notes:** After M004 proves SL/TP works in backtest, a future milestone will integrate into trading bot

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
| R032 | quality-attribute | deferred | none | none | unmapped |
| R033 | constraint | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 12
- Validated requirements: 18
- Deferred requirements: 1
- Out of scope: 2
- Total requirements: 33
- Mapped to slices: 30
- With proof: 25
- Unmapped active requirements: 9

## Deferred

### R032: Trailing stop loss (dynamic SL that moves with profit)

- **Class:** quality-attribute
- **Status:** deferred
- **Why:** More sophisticated exit logic; defer until fixed SL/TP proves useful
- **Source:** research
- **Primary Owner:** none
- **Supporting Slices:** none
- **Validation:** unmapped
- **Notes:** May be valuable for momentum strategies; revisit after M004 results

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

### R033: Live trading bot integration of SL/TP (this milestone is backtest-only)

- **Class:** constraint
- **Status:** out-of-scope
- **Why:** Milestone scope is backtest analysis only; live trading integration is a future milestone
- **Source:** inferred
- **Primary Owner:** none
- **Supporting Slices:** none
- **Validation:** n/a
- **Notes:** After M004 proves SL/TP works in backtest, a future milestone will integrate into trading bot

