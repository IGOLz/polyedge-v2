---
estimated_steps: 4
estimated_files: 1
---

# T03: Write verification script and prove registry discovery

**Slice:** S01 — Clean slate + strategy scaffolding
**Milestone:** M003

## Description

Deliver the slice's verification contract by writing a comprehensive bash script that checks all S01 must-haves: old strategies deleted, TEMPLATE updated, new folders created with correct structure, and most importantly — the registry can discover and instantiate all 7 new strategies.

This proves the scaffolding works end-to-end and satisfies the slice's demo: running `discover_strategies()` finds all 7 + TEMPLATE, and each can be instantiated with correct IDs.

## Steps

1. Create `scripts/verify_s01_scaffolding.sh` with bash script structure
2. Add checks for:
   - Old S1, S2 deletion: `! test -d src/shared/strategies/S1 && ! test -d src/shared/strategies/S2`
   - TEMPLATE updates: `get_param_grid` function exists in config.py
   - New folders: all 7 strategy folders exist with required files
   - Registry discovery: Python snippet calling `discover_strategies()` and asserting all 7 + TEMPLATE are found
   - Instantiation: Python snippet calling `get_strategy('S1')` through `get_strategy('S7')` and checking `strategy_id` and `strategy_name` match expected values from naming map
   - Stub behavior: Python snippet verifying each strategy's `evaluate()` returns `None` when called with a dummy MarketSnapshot
3. Make the script executable and ensure it exits 0 on full success, non-zero with clear error message on any failure
4. Run the script from the working directory and verify it passes

## Must-Haves

- [ ] `scripts/verify_s01_scaffolding.sh` exists and is executable
- [ ] Script checks old S1/S2 deletion
- [ ] Script checks TEMPLATE has `get_param_grid()`
- [ ] Script checks all 7 new strategy folders exist with `__init__.py`, `config.py`, `strategy.py`
- [ ] Script runs Python code to verify `discover_strategies()` finds all 7 + TEMPLATE (8 total strategies)
- [ ] Script runs Python code to verify each strategy can be instantiated with `get_strategy()` and has correct `strategy_id` and `strategy_name`
- [ ] Script runs Python code to verify each strategy's `evaluate()` returns `None` (stub behavior)
- [ ] Script exits 0 on success, non-zero on failure with informative error messages
- [ ] Running the script succeeds (all checks pass)

## Verification

- `test -x scripts/verify_s01_scaffolding.sh` — script is executable
- `bash scripts/verify_s01_scaffolding.sh` — exits 0, prints PASS messages for all checks
- Script output includes evidence of registry discovery and instantiation success

## Inputs

- `src/shared/strategies/` folder structure from T01 and T02
- S01-RESEARCH.md section "Verification Approach" — example verification commands
- S01-RESEARCH.md section "Strategy Naming Map" — expected IDs and names for assertion

## Expected Output

- `scripts/verify_s01_scaffolding.sh` — comprehensive verification script
- Script execution output showing all checks pass
- Proof that the slice's demo is true: registry discovers all 7 strategies, each can be instantiated, and evaluate returns None
