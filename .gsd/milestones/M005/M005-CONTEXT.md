# M005: Optimization Overhaul

**Gathered:** 2026-03-18
**Status:** Ready for planning

## Project Description

PolyEdge is a unified Polymarket trading platform. M004 delivered grid-search optimization with SL/TP, but the parameter grids are too sparse (648-1728 combos per strategy), output is too noisy, reports are too thin, and the optimizer crashes on Windows due to Unicode encoding. M005 fixes all of this and adds trailing stop loss.

## Why This Milestone

M004 proved the grid-search mechanism works, but the grids are too small to find real profitable configurations. The user's goal is to find parameter combinations that actually make money in live trading. That requires exhaustive exploration (millions of combos), actionable reports (top configs by multiple metrics), and practical usability (Windows support, clean progress output, documentation).

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run `python -m analysis.optimize --strategy S1` on Windows or Linux without encoding errors
- See millions of parameter combinations explored with parallel CPU utilization
- Read a rich Markdown report showing top 5 configs by composite score, by PnL, and by ROI
- See ROI computed with configurable bet size ($10 default)
- Explore trailing stop loss configurations alongside fixed SL
- Reference comprehensive CLI documentation for all optimizer flags and options

### Entry point / environment

- Entry point: `cd src && PYTHONPATH=. python -m analysis.optimize --strategy S1`
- Environment: local dev (Windows or Linux), requires TimescaleDB with market data
- Live dependencies involved: TimescaleDB database with historical market data

## Completion Class

- Contract complete means: dry-run shows 1M+ combos per strategy, encoding scan finds no non-ASCII in print/log, docs file exists with all flags
- Integration complete means: full optimization run completes with multiprocessing, produces rich report with ROI, trailing SL combos appear in results
- Operational complete means: runs on Windows (cp1252 encoding) without errors

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Full optimization run for at least one strategy completes with multiprocessing and produces a rich Markdown report with top 5 by score, PnL, and ROI
- Dry-run for all 7 strategies shows 1M+ combinations each, including trailing SL variants
- No non-ASCII characters in any print() or log statement in the analysis/ and shared/ Python files
- CLI documentation exists and covers all flags with examples

## Risks and Unknowns

- **Memory pressure at scale** — millions of metric dicts in RAM could exhaust memory. May need streaming to disk or chunked processing.
- **Multiprocessing serialization cost** — sharing market data (numpy arrays) across processes. May need shared memory or process-local copies via initializer.
- **Grid explosion for high-dimensional strategies** — S7 has 10 parameters; fine-grained steps could produce billions of combos. Need sensible per-strategy caps.

## Existing Codebase / Prior Art

- `src/analysis/optimize.py` — current single-threaded grid-search optimizer, prints full config per combo
- `src/analysis/backtest_strategies.py` — run_strategy() function that evaluates one config against all markets
- `src/analysis/backtest/engine.py` — Trade dataclass, compute_metrics(), simulate_sl_tp_exit(), save_module_results()
- `src/shared/strategies/S1-S7/config.py` — current param grids with 3 values per param
- `src/analysis/backtest/data_loader.py` — loads all market data from TimescaleDB into memory

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R034 — fine-grained grids producing 1M+ combos
- R035 — multiprocessing parallelization
- R036 — ROI metric with $10 default bet size
- R037 — rich Markdown reports (top 5 by score, PnL, ROI)
- R038 — batched progress output
- R039 — ASCII-safe output for Windows
- R040 — CLI documentation
- R041 — metrics-only storage (no per-config trade logs)
- R042 — trailing stop loss (opt-in, configurable trail distance)

## Scope

### In Scope

- Expand all 7 strategy param grids to 1M+ combinations with fine-grained steps
- Add trailing_sl (bool) and trail_distance (float) as grid-searchable exit parameters
- Implement trailing SL logic in simulate_sl_tp_exit()
- Rewrite optimizer to use multiprocessing (all CPU cores)
- Add ROI metric to compute_metrics() with configurable bet size
- Generate rich Markdown report per strategy (top 5 overall, by PnL, by ROI)
- Replace all non-ASCII characters in print/log statements across codebase
- Batched progress output (every Nth combo)
- Remove per-config trade log saving (metrics-only at scale)
- CLI documentation with all flags and examples
- Update TEMPLATE with trailing SL parameters

### Out of Scope / Non-Goals

- Live trading bot integration of trailing SL
- Changing strategy evaluate() logic
- Modifying core/ in any way
- Adding new strategies
- Changing the database schema

## Technical Constraints

- Must work on Windows (cp1252 encoding) and Linux
- Market data is loaded from TimescaleDB via asyncpg — loaded once, shared across workers
- Python multiprocessing (not threading) for CPU-bound parallelism
- Existing compute_metrics() return shape must be backward-compatible (new fields added, none removed)
- strategy.evaluate() is CPU-bound and GIL-releasing (numpy operations) — good parallelism candidate

## Integration Points

- TimescaleDB — market data source (read-only, unchanged)
- `analysis/backtest/engine.py` — simulate_sl_tp_exit() extended for trailing SL, compute_metrics() extended for ROI
- `analysis/backtest_strategies.py` — run_strategy() accepts new exit params
- `shared/strategies/*/config.py` — all param grids expanded
- `analysis/optimize.py` — rewritten for multiprocessing + new reporting

## Open Questions

- Optimal print interval for progress (every 50? every 100? auto-scale based on total?) — will auto-scale based on total combos, targeting ~100 progress updates per run
