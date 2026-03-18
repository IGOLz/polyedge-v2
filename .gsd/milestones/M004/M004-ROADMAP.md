# M004: Parameter Grid Optimization with Stop Loss & Take Profit

**Vision:** Transform backtesting from testing fixed-parameter strategies to exhaustive grid search across parameter combinations, with stop loss and take profit as universal exit parameters. Systematically explore the full parameter space and surface the top performers with explicit configuration values.

## Success Criteria

- Run `python3 -m analysis.optimize --strategy S1` and see 100+ parameter combinations tested (entry params × SL × TP grid)
- Output CSV shows top 10 ranked by performance with explicit stop_loss and take_profit values
- Each strategy (S1-S7) has complete `get_param_grid()` with SL/TP ranges
- TEMPLATE demonstrates the pattern for new strategies
- Trades distinguish SL exit vs TP exit vs hold-to-resolution in output
- Verification script proves all deliverables integrate correctly

## Key Risks / Unknowns

- **Parameter space explosion** — Adding SL (5 values) × TP (5 values) to existing entry param grids could create 1000+ combinations per strategy. Runtime could be prohibitive. Mitigation: Start conservative (3 values per SL/TP), test S1 first, adjust based on results.

- **Exit logic correctness** — Engine currently only supports hold-to-resolution. Adding SL/TP means tracking price every second and calculating PnL correctly for all exit paths.

## Proof Strategy

- Parameter space explosion → retire in S03 by testing S1 with full grid and measuring runtime; if >10min per strategy, reduce SL/TP value counts
- Exit logic correctness → retire in S02 by unit-testing SL/TP simulation with synthetic price data; verify PnL matches expected for early exits

## Verification Classes

- Contract verification: Tests verify SL/TP logic produces correct exit_reason and PnL; strategies import cleanly; TEMPLATE has SL/TP in grid
- Integration verification: Run optimize.py for S1 and verify output CSV has ranked combinations with SL/TP values
- Operational verification: none (backtest-only)
- UAT / human verification: User inspects top 10 output and confirms parameter values are explicit and useful for decision-making

## Milestone Definition of Done

This milestone is complete only when all are true:

- All 7 strategy folders (S1-S7) have `get_param_grid()` returning dicts with `stop_loss` and `take_profit` keys
- TEMPLATE/config.py demonstrates SL/TP pattern in example grid
- Engine has SL/TP exit simulation (checks price every second, exits early when threshold hit)
- Trade dataclass has `exit_reason` field with values 'sl', 'tp', or 'resolution'
- optimize.py generates Cartesian product including SL/TP dimensions
- Run `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` produces CSV with ≥100 combinations and top 10 include explicit SL/TP values
- Verification script proves: S1 grid includes SL/TP, dry-run shows dimensions, full run produces ranked output, at least one trade has exit_reason='sl' and one has 'tp'

## Requirement Coverage

- Covers: R023, R024, R025, R026, R027, R028, R029, R030, R031
- Partially covers: none
- Leaves for later: R032 (trailing stop loss)
- Orphan risks: none

## Slices

- [ ] **S01: Parameter Grid Foundation** `risk:low` `depends:[]`
  > After this: All 7 strategies (S1-S7) have `get_param_grid()` returning entry params + `stop_loss`/`take_profit` keys; TEMPLATE demonstrates pattern; fixture test verifies grids are non-empty and include SL/TP.

- [ ] **S02: Stop Loss & Take Profit Engine** `risk:medium` `depends:[S01]`
  > After this: Engine has `simulate_sl_tp_exit()` that scans price array and returns early exit second/price/reason when SL or TP hit; Trade dataclass extended with `exit_reason` field; unit tests prove correct PnL for SL/TP exits on synthetic data.

- [ ] **S03: Grid Search Orchestrator** `risk:low` `depends:[S02]`
  > After this: `optimize.py` extracts SL/TP from strategy grids, generates Cartesian product including exit params, passes SL/TP to engine when creating trades; dry-run for S1 shows ≥100 combinations.

- [ ] **S04: Ranking & Output** `risk:low` `depends:[S03]`
  > After this: Backtest output CSV includes `stop_loss`, `take_profit`, and `exit_reason` columns; top 10 summary prints explicit SL/TP values for each ranked combination; best config clearly surfaced.

- [ ] **S05: Integration Verification** `risk:low` `depends:[S04]`
  > After this: Verification script proves full pipeline: S1 grid includes SL/TP, dry-run shows dimensions, full optimize run produces CSV with ≥100 combinations, top 10 include explicit SL/TP, at least one trade has exit_reason='sl' and one has 'tp'.

## Boundary Map

### S01 → S02

Produces:
- `shared/strategies/S1-S7/config.py` — `get_param_grid()` returns dict with `stop_loss: [float, ...]` and `take_profit: [float, ...]` keys
- `shared/strategies/TEMPLATE/config.py` — Example grid includes SL/TP with comments
- Fixture test: `scripts/verify_m004_s01.py` — Imports all strategies, checks grid includes SL/TP

Consumes:
- nothing (first slice)

### S02 → S03

Produces:
- `analysis/backtest/engine.py` — `simulate_sl_tp_exit(prices, entry_second, entry_price, direction, stop_loss, take_profit) -> (exit_second, exit_price, exit_reason)`
- `analysis/backtest/engine.py` — `Trade` dataclass has new `exit_reason: str` field
- Unit test: `tests/test_sl_tp_engine.py` — Verifies SL/TP logic with synthetic price arrays

Consumes from S01:
- Strategy grids with SL/TP keys (used in later slices, not consumed directly by engine)

### S02 → S04

Produces:
- Engine functions and Trade extension consumed by output formatting

Consumes from S02:
- `simulate_sl_tp_exit()` function
- `Trade.exit_reason` field

### S03 → S04

Produces:
- `analysis/optimize.py` — Extends grid generation: reads SL/TP from strategy `get_param_grid()`, generates Cartesian product including exit params, passes to engine
- Updated `make_trade()` calls with SL/TP parameters

Consumes from S01:
- `get_param_grid()` return values with SL/TP keys

Consumes from S02:
- `simulate_sl_tp_exit()` for early exit detection
- `Trade.exit_reason` field for output

### S04 → S05

Produces:
- `analysis/optimize.py` — Output CSV includes `stop_loss`, `take_profit`, `exit_reason` columns
- `analysis/optimize.py` — Top 10 summary prints explicit SL/TP values
- Updated `compute_metrics()` to preserve SL/TP in output dict

Consumes from S03:
- Grid generation with SL/TP combinations
- Trade objects with exit_reason populated

### S05 (Integration Verification)

Produces:
- `scripts/verify_m004_milestone.sh` — Runs 7 checks proving full pipeline works

Consumes from S01-S04:
- All prior deliverables for end-to-end verification
