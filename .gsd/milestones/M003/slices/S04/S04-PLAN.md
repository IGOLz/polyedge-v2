# S04: Operator playbook + verification

**Goal:** Deliver operator playbook that teaches users how to run, interpret, and make deployment decisions from backtest output, plus final verification script proving all M003 deliverables integrate correctly.

**Demo:** User can (1) copy-paste playbook commands to run backtests on each strategy individually or all strategies together, (2) interpret metrics using playbook guidance to decide which strategies have real edge vs. noise, (3) run `bash scripts/verify_m003_milestone.sh` which exits 0 confirming all M003 requirements are met.

## Must-Haves

- `src/docs/STRATEGY_PLAYBOOK.md` exists with Quick Start, CLI Reference, Strategy Reference Table, Metric Interpretation Guide, Go/No-Go Decision Framework, Parameter Optimization Guide, and Troubleshooting sections
- Playbook documents all 7 strategies (S1-S7) with entry conditions, parameter ranges, and behavioral characteristics
- Playbook explains what each metric means (Sharpe, Sortino, profit factor, win rate, drawdown, consistency) and what thresholds indicate profitability for 5-minute markets with fees
- Playbook includes copy-pasteable CLI commands for running single strategies and all strategies with common flag combinations
- `scripts/verify_m003_milestone.sh` exists and validates all M003 deliverables: old S1/S2 deleted, 7 new strategies exist with real implementations, TEMPLATE updated, engine has dynamic fees + slippage, backtest runner works, reports generated, optimizer discovers param grids, src/core/ untouched
- Verification script exits 0 on success, exits 1 with diagnostics on failure
- Verification script uses synthetic data only (no DB dependency per S02 forward intelligence)

## Proof Level

- This slice proves: **final-assembly** — All M003 systems integrate correctly and are ready for user operation
- Real runtime required: no (verification uses synthetic data)
- Human/UAT required: yes (user runs playbook commands against real DB data at their own pace post-milestone; this is not gated)

## Observability / Diagnostics

- **Verification script output**: `scripts/verify_m003_milestone.sh` prints structured check results (8 groups: file structure, imports, registry, fee dynamics, slippage, backtest execution, optimizer discovery, core immutability); each check reports PASS/FAIL with command/output on failure
- **Playbook completeness**: `grep` commands validate presence of required sections and strategy coverage; missing sections surface as grep exit 1
- **Failure visibility**: Verification script exits 1 on first failure with diagnostic message showing which check failed and why; playbook grep failures show which required content is missing
- **Inspection surface**: Playbook itself is human-readable markdown with table of contents, examples, and troubleshooting; verification script is bash with clear check labels

## Verification

- `bash scripts/verify_m003_milestone.sh` (exits 0 = all M003 deliverables verified; exits 1 with failure diagnostics on any check failure)
- `test -f src/docs/STRATEGY_PLAYBOOK.md` (playbook file exists)
- `grep -q "## Quick Start" src/docs/STRATEGY_PLAYBOOK.md` (playbook has required sections)
- `grep -q "Sharpe Ratio" src/docs/STRATEGY_PLAYBOOK.md` (playbook documents metrics)
- `grep -q "S1.*S2.*S3.*S4.*S5.*S6.*S7" src/docs/STRATEGY_PLAYBOOK.md` (playbook covers all 7 strategies)

## Integration Closure

- Upstream surfaces consumed:
  - S03 strategies (S1-S7 config/strategy modules, signal detection logic)
  - S02 engine (dynamic fee formula, slippage penalty, metrics computation)
  - S01 scaffolding (registry discovery, TEMPLATE)
  - `src/analysis/backtest_strategies.py` (CLI flags, report generation)
  - `src/analysis/optimize.py` (parameter grid optimizer)
  - `scripts/verify_s03_strategies.sh` (S03 verification pattern)
- New wiring introduced in this slice: none (S04 is documentation + verification only)
- What remains before the milestone is truly usable end-to-end: **nothing** — M003 is complete after S04; user can immediately run backtests using playbook guidance

## Tasks

- [x] **T01: Write operator playbook documenting all strategies, CLI usage, and metric interpretation** `est:45m`
  - Why: Delivers R019 (operator guidance for deployment decisions); without this, user has strategies but no knowledge of what "good" looks like or how to use the tools
  - Files: `src/docs/STRATEGY_PLAYBOOK.md` (new file, ~400-500 lines)
  - Do: Create comprehensive reference doc with 7 sections: (1) Quick Start with one-liner commands for single strategy and all strategies, (2) Strategy Reference Table covering S1-S7 with entry conditions and parameter ranges, (3) CLI Reference documenting all `backtest_strategies.py` and `optimize.py` flags with examples, (4) Metric Interpretation Guide explaining Sharpe/Sortino/profit factor/win rate/drawdown/consistency with formulas and thresholds for 5-minute markets, (5) Go/No-Go Decision Framework defining profitability thresholds (total_pnl > 0, Sharpe > 1.0, profit factor > 1.2, win rate > 52%, max drawdown < 50% of total PnL, consistency > 60), (6) Parameter Optimization Guide showing how to use optimizer to explore param grids, (7) Troubleshooting covering zero-trade strategies (S6 legitimately produces zero if no streaks), sparse data causing _get_price() to return None, DB dependency (worktree may be empty), optimizer runtime. Read strategy docstrings and config files to extract entry conditions and parameter semantics. Read engine.py compute_metrics() for metric formulas. Follow S03 forward intelligence notes on S6 cross-market limitation and S7 inline duplication. Add prerequisite note: real backtests require TimescaleDB data; if DB empty, strategies are correct but no data to backtest against.
  - Verify: `test -f src/docs/STRATEGY_PLAYBOOK.md && grep -q "Quick Start" src/docs/STRATEGY_PLAYBOOK.md && grep -q "Sharpe Ratio" src/docs/STRATEGY_PLAYBOOK.md && grep -q "S7" src/docs/STRATEGY_PLAYBOOK.md`
  - Done when: Playbook file exists with all 7 sections, covers all 7 strategies, documents all metrics with thresholds, includes copy-pasteable CLI commands, and addresses known limitations from S03

- [x] **T02: Write M003 milestone verification script covering all deliverables** `est:30m`
  - Why: Proves M003 definition of done is met; gates milestone completion with objective pass/fail test
  - Files: `scripts/verify_m003_milestone.sh` (new file, ~200-250 lines)
  - Do: Create bash script following `verify_s03_strategies.sh` pattern with 8 check groups: (1) File structure checks (old shared/strategies/S1/ and S2/ deleted, new S1-S7 exist with config.py and strategy.py, TEMPLATE exists), (2) Import checks (all 7 strategies import), (3) Registry discovery (7 strategies + TEMPLATE found), (4) Engine fee dynamics (polymarket_dynamic_fee(0.10) < polymarket_dynamic_fee(0.50) < polymarket_dynamic_fee(0.90) — fees vary by price), (5) Engine slippage (run make_trade() on synthetic market with slippage=0 vs slippage=0.01, confirm PnL differs), (6) Backtest execution (run backtest_strategies.py --strategy S1 on synthetic MarketSnapshot data without DB, confirm no crashes), (7) Optimizer discovery (run optimize.py --strategy S1 --dry-run, confirm param grid printed), (8) Core immutability (git diff main..HEAD src/core/ produces no changes or HEAD is main). Use Python heredocs for programmatic checks. Exit 0 on all checks passed, exit 1 with diagnostics on any failure. Checks 4-6 must use synthetic data only (no DB queries) per S02 forward intelligence. Script runs from repo root with PYTHONPATH=src.
  - Verify: `bash scripts/verify_m003_milestone.sh` (exits 0)
  - Done when: Verification script exists, covers all 8 check groups from M003 definition of done, uses synthetic-only data for backtest checks, and exits 0 when run in clean worktree

## Files Likely Touched

- `src/docs/STRATEGY_PLAYBOOK.md` (new)
- `scripts/verify_m003_milestone.sh` (new)
