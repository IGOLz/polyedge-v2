# M004: Parameter Grid Optimization with Stop Loss & Take Profit

**Gathered:** 2026-03-18
**Status:** Ready for planning

## Project Description

Transform backtesting from testing fixed-parameter strategies to exhaustive grid search across parameter combinations. Each strategy declares tunable parameters (entry thresholds, windows, etc.) plus universal stop loss and take profit ranges. The analysis module tests ALL COMBINATIONS and surfaces the top 10 performers with explicit parameter values.

## Why This Milestone

User ran M003 strategies and discovered they don't work — not because the logic is wrong, but because they use **fixed parameters**. A strategy hardcoded to "buy when price is 0.70" never tests 0.71, 0.72, etc. Without systematic parameter exploration, we're flying blind. This milestone makes parameters **variable** and lets data decide what works.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run `python3 -m analysis.optimize --strategy S1` and see 100+ parameter combinations tested
- Get ranked output showing top 10 combinations with explicit entry parameters, stop loss, and take profit values
- See which parameter sets drove performance (e.g., "best config: price_threshold=0.72, SL=0.45, TP=0.85")
- Distinguish trades that exited via stop loss vs take profit vs hold-to-resolution
- Apply the same grid search pattern to any new strategy using updated TEMPLATE

### Entry point / environment

- Entry point: `python3 -m analysis.optimize --strategy <SID>` CLI command from `src/` directory
- Environment: Local dev with TimescaleDB access
- Live dependencies involved: PostgreSQL/TimescaleDB for historical price data

## Completion Class

- Contract complete means: All 7 strategies have `get_param_grid()` with entry params + SL/TP; TEMPLATE demonstrates pattern; engine has SL/TP exit logic; optimize.py generates combinations
- Integration complete means: Run optimize.py for S1 and see ranked output with top 10 combinations including SL/TP values; trades marked with exit_reason
- Operational complete means: none (backtest-only milestone)

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Run `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run` shows parameter grid with SL/TP dimensions
- Run full optimization (without --dry-run) produces CSV with ≥100 combinations tested
- Top 10 output includes explicit stop_loss and take_profit values for each combination
- At least one trade in output has exit_reason='sl' and another has exit_reason='tp'
- S1-S7 all import cleanly and have non-empty `get_param_grid()` return values
- TEMPLATE/config.py demonstrates the SL/TP pattern

## Risks and Unknowns

- **SL/TP parameter space explosion** — If each strategy has 5 entry params with 3 values each (243 combos) and we add SL (5 values) × TP (5 values), we're at 6,075 combinations per strategy. Runtime might be prohibitive for all 7 strategies. Mitigation: Start with conservative grids (2-3 values per SL/TP), test on S1 first, adjust ranges based on results.

- **Exit logic complexity** — Current engine only supports "hold to resolution" or hardcoded mid-market exits. Adding SL/TP means tracking price every second and exiting early when thresholds hit. Need to ensure PnL calculation is correct for all exit paths.

## Existing Codebase / Prior Art

- `src/analysis/optimize.py` — Already does grid search on entry parameters; needs extension to inject SL/TP into every grid
- `src/analysis/backtest/engine.py` — Already has `make_trade()` with `second_exited` and `exit_price` parameters; needs SL/TP simulation logic
- `src/shared/strategies/S1-S7/config.py` — Each has `get_param_grid()` returning entry parameter ranges; need to add SL/TP keys
- `src/shared/strategies/TEMPLATE/config.py` — Demonstrates pattern for new strategies; needs SL/TP in example grid
- Legacy `analysis/strategies/strategy_momentum.py` has stop_loss logic but in old codebase; can reference for implementation patterns but not reuse directly

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R023 — Each strategy declares tunable parameters via `get_param_grid()`
- R024 — Stop loss and take profit are universal exit parameters in every strategy's grid
- R025 — Engine executes SL/TP exit logic during backtest
- R026 — Grid search orchestrator generates all parameter combinations (entry params × SL × TP)
- R027 — Output ranks combinations by performance and surfaces top 10 per strategy
- R028 — Output shows best parameter configuration with explicit SL/TP values
- R029 — All 7 existing strategies (S1-S7) updated with complete parameter grids including SL/TP
- R030 — TEMPLATE updated to demonstrate parameter grid pattern with SL/TP
- R031 — Backtest output clearly distinguishes between "hold to resolution" and "SL/TP exit" trades

## Scope

### In Scope

- Add `stop_loss` and `take_profit` keys to every strategy's `get_param_grid()` return value
- Update `optimize.py` to generate Cartesian product including SL/TP dimensions
- Add SL/TP exit simulation to backtest engine (check price every second, exit early when threshold hit)
- Mark trades with `exit_reason` field ('sl', 'tp', 'resolution')
- Update TEMPLATE to demonstrate SL/TP pattern
- Update all 7 strategies (S1-S7) with SL/TP parameter ranges
- Verification script proving full pipeline works

### Out of Scope / Non-Goals

- Live trading bot integration (backtest-only milestone)
- Trailing stop loss (deferred to future milestone if needed)
- Optimization beyond grid search (e.g., Bayesian optimization, genetic algorithms)
- Cross-strategy ensemble optimization (testing combinations of multiple strategies together)

## Technical Constraints

- Must preserve backward compatibility: strategies without SL/TP in grid should still work (default to hold-to-resolution)
- Parameter space explosion: each SL/TP value multiplies combinations — keep grids conservative (3-5 values per param)
- Engine must handle all three exit paths correctly: SL, TP, and resolution
- PYTHONPATH=. requirement for all CLI commands remains

## Integration Points

- `shared/strategies/S1-S7/config.py` — Add SL/TP to `get_param_grid()`
- `shared/strategies/TEMPLATE/config.py` — Update example grid with SL/TP
- `analysis/optimize.py` — Extend grid generation to include SL/TP from strategy config
- `analysis/backtest/engine.py` — Add `simulate_sl_tp_exit()` function or equivalent
- `analysis/backtest/engine.py` — Extend `Trade` dataclass with `exit_reason` field
- `analysis/backtest_strategies.py` — Pass SL/TP params to engine when creating trades

## Open Questions

- **SL/TP as absolute prices or relative offsets?** — Should stop_loss=0.45 mean "exit if price drops to 0.45" (absolute) or "exit if price drops 0.05 below entry" (relative)? Current thinking: Absolute prices are simpler and match how user described it ("sell at 0.70"). Relative offsets could be added later if needed.

- **How to handle SL > TP or invalid ranges?** — If a parameter combination generates stop_loss=0.60 and take_profit=0.50 for an Up bet, that's nonsensical. Should we skip invalid combinations or clamp them? Current thinking: Skip invalid combinations during grid generation to avoid wasted backtests.

- **Should SL/TP be strategy-specific or universal?** — Different entry patterns might need different exit thresholds. Current thinking: Strategy-specific (each strategy declares its own SL/TP range in `get_param_grid()`) gives more flexibility than universal engine-level params.
