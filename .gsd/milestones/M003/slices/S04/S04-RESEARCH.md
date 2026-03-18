# S04 — Operator playbook + verification — Research

**Date:** 2026-03-18

## Summary

S04 produces two deliverables: (1) an operator playbook (`src/docs/STRATEGY_PLAYBOOK.md`) that teaches the user how to run, interpret, and make deployment decisions from backtest output, and (2) a final verification script that confirms all M003 deliverables work end-to-end.

This is straightforward documentation and integration testing work. All the underlying systems are complete from S01-S03. The playbook documents existing CLI tools (`backtest_strategies.py`, `optimize.py`) and explains what the output metrics mean. The verification script ties together checks from S01/S03 and adds new integration checks that prove the full backtest pipeline works.

The playbook is the user-facing artifact that makes M003 useful. Without it, the user has 7 strategies and a backtest runner but no guidance on what "good" looks like or how to decide what to deploy. The verification script is the acceptance gate — it proves everything from S01-S03 actually integrates correctly.

## Recommendation

**Playbook structure:**
1. **Quick Start** — One-liner commands to run a single strategy or all strategies
2. **Strategy Reference Table** — Per-strategy entry conditions, typical behavior, parameter sensitivity
3. **CLI Reference** — All flags for `backtest_strategies.py` and `optimize.py` with examples
4. **Metric Interpretation Guide** — What each metric means and what thresholds indicate profitability for 5-minute markets
5. **Go/No-Go Decision Framework** — How to decide if a strategy is worth deploying live
6. **Parameter Optimization Guide** — How to use the optimizer to explore param grids
7. **Troubleshooting** — Common failure modes (zero trades, sparse data, DB issues)

**Verification script coverage:**
1. Import checks (all strategies load)
2. Registry discovery (7 strategies + TEMPLATE found)
3. Engine fee dynamics (different prices produce different fees)
4. Engine slippage (PnL changes with slippage parameter)
5. Backtest execution (each strategy runs against synthetic data without errors)
6. Report generation (JSON + Markdown reports produced)
7. Optimizer dry-run (param grid discovery works)
8. Core immutability (src/core/ untouched since M001)

Write verification as a bash script matching the pattern from `scripts/verify_s03_strategies.sh` — Python heredocs for programmatic checks, clear success/failure output, exit 0 on pass.

## Implementation Landscape

### Key Files

**New files to create:**
- `src/docs/STRATEGY_PLAYBOOK.md` — Operator guide (300-500 lines, comprehensive reference doc)
- `scripts/verify_m003_milestone.sh` — Final verification script covering all M003 deliverables

**Existing files to reference (read-only in playbook):**
- `src/analysis/backtest_strategies.py` — CLI entry point, already has all flags and report generation
- `src/analysis/optimize.py` — Parameter grid optimizer, already has dry-run mode
- `src/analysis/backtest/engine.py` — Metrics computation (`compute_metrics()`), fee/slippage functions
- `src/shared/strategies/report.py` — StrategyReport structure (what reports contain)
- `src/shared/strategies/S1/` through `S7/` — Strategy implementations (entry conditions, param grids)
- `scripts/verify_s03_strategies.sh` — Pattern for verification structure

### Build Order

1. **Document metric definitions first** — This is core knowledge for interpreting any backtest. Write the "Metric Interpretation Guide" section explaining Sharpe, Sortino, profit factor, win rate, drawdown, consistency, ranking score. Include formulas and thresholds.

2. **Document CLI commands** — Write "Quick Start" and "CLI Reference" sections showing how to run backtests with all flags (`--strategy`, `--assets`, `--slippage`, `--fee-base-rate`). Include examples for single strategy, all strategies, asset filtering, optimizer usage.

3. **Document strategy characteristics** — Read each strategy's config/strategy files to extract entry conditions, parameter ranges, and behavioral notes. Create "Strategy Reference Table" with per-strategy details. Note S6's cross-market limitation, S7's inline duplication, parameter grid sizes.

4. **Write go/no-go framework** — This is judgment-based. For 5-minute markets with dynamic fees + slippage, define thresholds: total_pnl > 0, Sharpe > 1.0, profit factor > 1.2, win rate > 52%, max drawdown < 50% of total PnL, consistency > 60. Explain why these matter.

5. **Write troubleshooting section** — Document known failure modes from S03 forward intelligence: zero trades for S6 if streak patterns don't exist, sparse data causing _get_price() to return None, DB dependency (worktree DB may be empty), optimizer runtime warnings.

6. **Build verification script** — Start from `verify_s03_strategies.sh` pattern. Add checks for:
   - Fee dynamics: `polymarket_dynamic_fee(0.10)` < `polymarket_dynamic_fee(0.50)` < `polymarket_dynamic_fee(0.90)`
   - Slippage impact: run same synthetic market with slippage=0 vs slippage=0.01, confirm PnL differs
   - Backtest execution: run `backtest_strategies.py --strategy S1` on synthetic market data (no DB), confirm reports generated
   - Optimizer discovery: run `optimize.py --strategy S1 --dry-run`, confirm param grid printed
   - Core immutability: `git diff --stat M001..HEAD src/core/` produces no changes

### Verification Approach

**Playbook verification:** User acceptance (not scriptable) — user copy-pastes commands and confirms output matches descriptions. Mark in playbook: "These commands assume you have DB data; if worktree DB is empty, see Troubleshooting."

**Milestone verification script:** Must run without DB dependency (S02 forward intelligence warned worktree DB is empty). Use synthetic data for backtest checks. Script exit 0 = M003 complete, all requirements satisfied.

**Final acceptance command:**
```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003
bash scripts/verify_m003_milestone.sh
```

If exit 0, M003 is done. User can then run real backtests at their own pace using the playbook commands.

## Constraints

- **No database dependency for verification:** S02 forward intelligence confirmed worktree TimescaleDB is empty. Verification script must use synthetic market data, not real DB queries. Document this limitation in verification script comments.

- **Playbook must work with empty DB:** Some CLI examples will fail if user doesn't have DB data. Add "Prerequisites" section to playbook: "Real backtests require historical data in TimescaleDB. If you see 'No markets loaded', your DB is empty — strategies are correct but there's no data to backtest against."

- **Strategy metadata lives in code, not config:** Entry conditions, parameter semantics, behavioral notes are in strategy docstrings and comments, not in a structured config file. Research must read strategy source files to extract this information.

- **No modification to strategy implementations:** S04 is documentation-only. If we find a strategy bug during research, note it in the playbook troubleshooting section but don't fix it — that's out of scope.

## Common Pitfalls

- **Over-documenting implementation details:** Playbook is for operators (users deciding what to deploy), not developers (people modifying strategies). Focus on "what does this strategy do" and "how do I interpret results", not "how does _get_price() work internally".

- **Prescriptive thresholds without context:** Saying "Sharpe > 2.0 means good" without explaining why is cargo-cult guidance. Explain that 5-minute markets with fees have thin edges, so Sharpe 1.0-1.5 is realistic for profitable strategies, and Sharpe > 2.0 is exceptional.

- **Ignoring zero-trade strategies:** S6 may legitimately produce zero trades if streak patterns don't exist in the data. This is correct behavior, not a bug. Playbook must normalize this — "Zero trades means the strategy found no entry opportunities matching its criteria. This is expected for some strategies on some datasets."

- **Verification script that requires DB:** S02 verification removed DB fixture creation because worktree DB is empty. If M003 verification tries to run real backtests against DB, it will fail. Use synthetic MarketSnapshot data for all backtest checks.

## Open Risks

**None** — S04 is low-risk documentation and verification work. All underlying systems are complete and verified in S01-S03. If the playbook commands don't work, it's because we documented them wrong, not because the systems are broken.

## Sources

- Metric formulas: `src/analysis/backtest/engine.py` (compute_metrics function, lines 116-216)
- CLI flags: `src/analysis/backtest_strategies.py` (argparse setup, lines 199-244)
- Strategy characteristics: `src/shared/strategies/S1/` through `S7/` (config.py and strategy.py docstrings)
- Verification pattern: `scripts/verify_s03_strategies.sh` (S03 verification structure)
- Report structure: `src/shared/strategies/report.py` (StrategyReport fields and to_markdown rendering, lines 47-220)
- S03 forward intelligence: `.gsd/milestones/M003/slices/S03/S03-SUMMARY.md` (what needs documenting, known limitations)
- M003 definition of done: `.gsd/milestones/M003/M003-ROADMAP.md` (verification acceptance criteria)
