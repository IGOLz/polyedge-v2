---
estimated_steps: 5
estimated_files: 5
---

# T01: Delete old strategies and update TEMPLATE

**Slice:** S01 — Clean slate + strategy scaffolding
**Milestone:** M003

## Description

Clear out the disposable proof-of-concept strategies (S1 spike reversion, S2 volatility) that are being replaced in M003. Update the TEMPLATE folder to include the new strategy shape: a `get_param_grid()` function for parameter optimization, and updated README emphasizing that param grid is now a required component.

This establishes the clean baseline that all 7 new strategies will inherit when T02 copies the TEMPLATE.

## Steps

1. Delete `src/shared/strategies/S1/` folder entirely (old spike reversion strategy)
2. Delete `src/shared/strategies/S2/` folder entirely (old volatility strategy)
3. Add `get_param_grid()` function to `src/shared/strategies/TEMPLATE/config.py` using the exact skeleton from S01-RESEARCH.md (returns empty dict with docstring explaining grid-search usage and example)
4. Update `src/shared/strategies/TEMPLATE/README.md` section 6: change title from "(Optional) Add `get_param_grid()`" to "Add `get_param_grid()` for parameter optimization" and add note that all strategies should define a param grid even if it starts empty
5. Verify deletions and additions with quick bash checks

## Must-Haves

- [ ] `src/shared/strategies/S1/` no longer exists
- [ ] `src/shared/strategies/S2/` no longer exists
- [ ] `src/shared/strategies/TEMPLATE/config.py` contains `get_param_grid()` function with correct signature and docstring
- [ ] `src/shared/strategies/TEMPLATE/README.md` section 6 title updated to remove "(Optional)" and emphasize param grid is required

## Verification

- `! test -d src/shared/strategies/S1` — old S1 deleted
- `! test -d src/shared/strategies/S2` — old S2 deleted
- `grep -q "def get_param_grid" src/shared/strategies/TEMPLATE/config.py` — function exists
- `grep -q "## 6. Add \`get_param_grid()\`" src/shared/strategies/TEMPLATE/README.md` — section title updated (no "Optional")

## Inputs

- `src/shared/strategies/S1/` — existing old strategy folder to delete
- `src/shared/strategies/S2/` — existing old strategy folder to delete
- `src/shared/strategies/TEMPLATE/config.py` — existing template config to update
- `src/shared/strategies/TEMPLATE/README.md` — existing template README to update
- S01-RESEARCH.md section "TEMPLATE Updates" — exact code snippets for `get_param_grid()` skeleton and README changes

## Expected Output

- `src/shared/strategies/S1/` and `S2/` deleted
- `src/shared/strategies/TEMPLATE/config.py` updated with `get_param_grid()` function
- `src/shared/strategies/TEMPLATE/README.md` section 6 updated to make param grid non-optional
