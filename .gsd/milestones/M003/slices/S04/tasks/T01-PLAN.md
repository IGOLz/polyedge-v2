---
estimated_steps: 7
estimated_files: 8
---

# T01: Write operator playbook documenting all strategies, CLI usage, and metric interpretation

**Slice:** S04 — Operator playbook + verification
**Milestone:** M003

## Description

Create comprehensive operator playbook (`src/docs/STRATEGY_PLAYBOOK.md`) that teaches users how to run backtests, interpret performance metrics, and make deployment decisions based on results. This is the primary user-facing documentation for M003 — it bridges the gap between "strategies exist" and "user can evaluate them independently".

The playbook must cover:
1. **Quick Start** — Copy-paste commands to immediately run backtests
2. **Strategy Reference** — Per-strategy entry logic, parameters, and behavioral notes
3. **CLI Reference** — All flags for backtest_strategies.py and optimize.py
4. **Metric Interpretation** — What Sharpe/Sortino/profit factor/etc. mean and what values indicate real edge
5. **Go/No-Go Framework** — Concrete thresholds for deployment decisions
6. **Optimization Guide** — How to explore parameter grids
7. **Troubleshooting** — Common failure modes (zero trades, sparse data, empty DB)

This task delivers R019 (operability: backtest output includes clear profitability metrics and go/no-go guidance).

## Steps

1. Create `src/docs/` directory if it doesn't exist
2. Read S1-S7 strategy docstrings and config files to extract entry conditions, parameter ranges, and detect any special notes (S6 cross-market limitation, S7 inline duplication)
3. Read `src/analysis/backtest/engine.py` compute_metrics() function to extract metric formulas and understand what each metric measures
4. Read `src/analysis/backtest_strategies.py` CLI argument parser to document all available flags (--strategy, --assets, --durations, --slippage, --fee-base-rate, --output-dir)
5. Write playbook with 7 sections following structure defined in slice plan, using actual strategy characteristics from step 2, actual metric formulas from step 3, and actual CLI flags from step 4
6. Add prerequisites section noting real backtests require TimescaleDB data; if worktree DB is empty, strategies are correct but there's no data to backtest against
7. Include troubleshooting entries for S03 forward intelligence items: S6 zero trades when no streak patterns exist, sparse data causing _get_price() to return None, optimizer runtime (72-192 combinations × market count)

## Must-Haves

- [ ] Playbook file exists at `src/docs/STRATEGY_PLAYBOOK.md`
- [ ] Quick Start section with one-liner commands for single strategy and all strategies
- [ ] Strategy Reference Table covering all 7 strategies (S1-S7) with entry conditions, typical parameter ranges, and behavioral notes
- [ ] CLI Reference documenting all backtest_strategies.py and optimize.py flags with example usage
- [ ] Metric Interpretation Guide explaining Sharpe, Sortino, profit factor, win rate, max drawdown, consistency with formulas and context for 5-minute markets with fees
- [ ] Go/No-Go Decision Framework defining profitability thresholds (total_pnl > 0, Sharpe > 1.0, profit factor > 1.2, win rate > 52%, max drawdown < 50% of total PnL, consistency > 60) with rationale
- [ ] Parameter Optimization Guide showing how to run optimizer and interpret grid search results
- [ ] Troubleshooting section addressing zero-trade strategies, sparse data failures, empty DB, and optimizer runtime
- [ ] Prerequisites note about DB dependency

## Verification

- `test -f src/docs/STRATEGY_PLAYBOOK.md` confirms file exists
- `wc -l src/docs/STRATEGY_PLAYBOOK.md` shows ~400-500 lines (comprehensive reference doc)
- `grep -q "## Quick Start" src/docs/STRATEGY_PLAYBOOK.md` confirms section exists
- `grep -q "## Strategy Reference" src/docs/STRATEGY_PLAYBOOK.md` confirms section exists
- `grep -q "## Metric Interpretation" src/docs/STRATEGY_PLAYBOOK.md` confirms section exists
- `grep -q "Sharpe Ratio" src/docs/STRATEGY_PLAYBOOK.md` confirms metric documentation
- `grep -c "^### S[1-7]" src/docs/STRATEGY_PLAYBOOK.md` equals 7 (all strategies covered in reference table)
- `grep -q "total_pnl > 0" src/docs/STRATEGY_PLAYBOOK.md` confirms go/no-go thresholds documented
- `grep -q "Prerequisites" src/docs/STRATEGY_PLAYBOOK.md` confirms DB dependency noted

## Inputs

- `src/shared/strategies/S1/strategy.py` through `S7/strategy.py` — strategy docstrings containing entry logic descriptions
- `src/shared/strategies/S1/config.py` through `S7/config.py` — parameter definitions and get_param_grid() implementations
- `src/analysis/backtest/engine.py` — compute_metrics() function with metric formulas (lines 116-216)
- `src/analysis/backtest_strategies.py` — argparse CLI definitions (lines 199-244)
- `src/analysis/optimize.py` — optimizer CLI and usage patterns
- `.gsd/milestones/M003/slices/S03/S03-SUMMARY.md` — forward intelligence on S6/S7 limitations, parameter grid sizes, zero-trade scenarios
- `.gsd/milestones/M003/slices/S03/S03-RESEARCH.md` — strategy family descriptions and research grounding

## Expected Output

- `src/docs/STRATEGY_PLAYBOOK.md` — comprehensive operator reference doc (~400-500 lines) with 7 main sections, copy-pasteable commands, metric definitions with formulas, profitability thresholds with rationale, per-strategy characteristics table, troubleshooting guide, and prerequisites note about DB dependency
