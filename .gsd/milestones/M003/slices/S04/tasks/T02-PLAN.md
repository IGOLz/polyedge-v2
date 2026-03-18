---
estimated_steps: 8
estimated_files: 4
---

# T02: Write M003 milestone verification script covering all deliverables

**Slice:** S04 — Operator playbook + verification
**Milestone:** M003

## Description

Create final milestone verification script (`scripts/verify_m003_milestone.sh`) that proves all M003 deliverables integrate correctly and meet the milestone definition of done. This is the acceptance gate — exit 0 means M003 is complete and all requirements are satisfied.

The verification script validates 8 categories:
1. **File structure** — old S1/S2 deleted, new S1-S7 exist, TEMPLATE updated
2. **Import checks** — all 7 strategies import without errors
3. **Registry discovery** — 7 strategies + TEMPLATE discovered
4. **Engine fee dynamics** — fees vary by price (dynamic formula working)
5. **Engine slippage** — PnL changes with slippage parameter
6. **Backtest execution** — strategies run through backtest_strategies.py without crashes
7. **Optimizer discovery** — param grids discovered correctly
8. **Core immutability** — src/core/ unchanged since M001 (R010 constraint)

Must use synthetic data only for checks 4-6 (no DB dependency per S02 forward intelligence that worktree DB is empty).

## Steps

1. Read `scripts/verify_s03_strategies.sh` to understand verification script pattern (Python heredocs, clear output format, exit code semantics)
2. Create `scripts/verify_m003_milestone.sh` starting with bash shebang, error handling, and working directory setup matching S03 pattern
3. Write Check 1 (File structure): bash commands to verify old strategies/S1/ and strategies/S2/ don't exist in src/shared/, new S1-S7 folders exist with config.py and strategy.py, TEMPLATE folder exists
4. Write Check 2 (Import checks): Python heredoc importing all 7 strategies (config + strategy modules), report success/failure per strategy, exit 1 if any fail
5. Write Check 3 (Registry discovery): Python heredoc calling discover_strategies(), verify exactly 8 discovered (S1-S7 + TEMPLATE), exit 1 if count wrong
6. Write Check 4 (Engine fee dynamics): Python heredoc importing polymarket_dynamic_fee from engine, compute fees at prices 0.10, 0.50, 0.90, verify fee(0.10) < fee(0.50) and fee(0.50) > fee(0.90) (proving fee varies by price and peaks near 0.50)
7. Write Check 5 (Engine slippage): Python heredoc creating synthetic market dict, calling make_trade() twice with same inputs except slippage=0.0 vs slippage=0.01, verify PnL differs (proving slippage affects profitability)
8. Write Check 6 (Backtest execution): Python heredoc creating synthetic MarketSnapshot (300 seconds, price array with non-NaN values), instantiating S1 strategy, calling evaluate(), verify it returns None or Signal without crashing (no DB required)
9. Write Check 7 (Optimizer discovery): Python heredoc importing S1 config, calling get_param_grid(), verify returned dict has ≥2 parameters and each parameter has ≥2 values
10. Write Check 8 (Core immutability): bash command `git diff main..HEAD -- src/core/` (or `git diff M001..HEAD -- src/core/` if M001 tag exists), verify output is empty (src/core/ untouched), handle case where HEAD is main (no diff expected)
11. Add summary output at end: "All M003 verification checks passed" and exit 0 if all checks succeeded, exit 1 with diagnostic output if any check failed

## Must-Haves

- [ ] Script exists at `scripts/verify_m003_milestone.sh` with executable permissions
- [ ] Check 1: File structure validation (old deleted, new exist, TEMPLATE updated)
- [ ] Check 2: All 7 strategies import successfully
- [ ] Check 3: Registry discovers exactly 8 strategies (S1-S7 + TEMPLATE)
- [ ] Check 4: Engine fee dynamics proven (fees vary by price)
- [ ] Check 5: Engine slippage impact proven (PnL differs with slippage parameter)
- [ ] Check 6: Backtest execution works on synthetic data (no DB dependency)
- [ ] Check 7: Optimizer param grid discovery works (all grids have ≥2 params with ≥2 values each)
- [ ] Check 8: src/core/ immutability verified (R010 constraint satisfied)
- [ ] Script exits 0 on success, exits 1 with clear diagnostics on any failure
- [ ] All checks use synthetic data only (no TimescaleDB queries)

## Verification

- `test -f scripts/verify_m003_milestone.sh` confirms file exists
- `test -x scripts/verify_m003_milestone.sh` confirms executable permissions
- `bash scripts/verify_m003_milestone.sh` exits 0 (all checks pass)
- `grep -c "Check [0-9]:" scripts/verify_m003_milestone.sh` equals 8 (all check groups present)
- `grep -q "polymarket_dynamic_fee" scripts/verify_m003_milestone.sh` confirms fee dynamics check exists
- `grep -q "make_trade" scripts/verify_m003_milestone.sh` confirms slippage check exists
- `grep -q "src/core/" scripts/verify_m003_milestone.sh` confirms immutability check exists

## Inputs

- `scripts/verify_s03_strategies.sh` — pattern for verification script structure (bash + Python heredocs, clear output, exit code handling)
- `src/analysis/backtest/engine.py` — polymarket_dynamic_fee() function, make_trade() function, Trade dataclass structure
- `src/shared/strategies/registry.py` — discover_strategies() function
- `src/shared/strategies/base.py` — MarketSnapshot dataclass for synthetic data construction
- `src/shared/strategies/S1/config.py` — get_param_grid() example for optimizer check
- `.gsd/milestones/M003/M003-ROADMAP.md` — milestone definition of done (what must be verified)
- `.gsd/REQUIREMENTS.md` — R010 constraint (src/core/ immutability)

## Expected Output

- `scripts/verify_m003_milestone.sh` — executable bash script (~200-250 lines) with 8 check groups validating all M003 deliverables, using Python heredocs for programmatic checks, exiting 0 on success with summary message "All M003 verification checks passed", exiting 1 with detailed diagnostics on any failure, using synthetic-only data for all backtest checks (no DB dependency)
