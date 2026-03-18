---
id: T01
parent: S01
milestone: M003
provides:
  - Clean slate with old S1/S2 strategies removed
  - Updated TEMPLATE with get_param_grid() skeleton
  - Template README emphasizing param grid as required component
key_files:
  - src/shared/strategies/TEMPLATE/config.py
  - src/shared/strategies/TEMPLATE/README.md
key_decisions: []
patterns_established:
  - All new strategies must define get_param_grid() for optimizer compatibility
observability_surfaces:
  - File system structure (ls src/shared/strategies/)
  - grep checks for get_param_grid() presence
  - README section 6 title indicates requirement status
duration: 4m
verification_result: passed
completed_at: 2026-03-18T14:08:00+01:00
blocker_discovered: false
---

# T01: Delete old strategies and update TEMPLATE

**Deleted disposable S1/S2 strategies and added get_param_grid() skeleton to TEMPLATE, establishing the baseline for 7 new research-backed strategies.**

## What Happened

Executed a clean-slate operation to prepare for M003's new strategy suite:

1. **Deleted old strategies**: Removed `src/shared/strategies/S1/` (spike reversion) and `src/shared/strategies/S2/` (volatility) entirely, clearing space for the new research-backed implementations.

2. **Added param grid function**: Inserted the `get_param_grid()` skeleton to `TEMPLATE/config.py` with full docstring explaining grid-search usage, example usage, and return contract. Returns empty dict by default with clear documentation that real parameters should replace it.

3. **Updated template documentation**: Modified `TEMPLATE/README.md` section 6 to remove "(Optional)" from the title and add explicit guidance that all strategies should define a parameter grid even if it starts empty. This establishes param grid as a first-class requirement for new strategies.

All changes follow the exact specifications from S01-RESEARCH.md. The TEMPLATE now provides a complete scaffold that T02 will copy to create 7 new strategy folders.

## Verification

Ran four verification checks from the task plan:

1. **S1 deletion**: `! test -d src/shared/strategies/S1` — passed
2. **S2 deletion**: `! test -d src/shared/strategies/S2` — passed
3. **Function presence**: `grep -q "def get_param_grid" src/shared/strategies/TEMPLATE/config.py` — passed
4. **README update**: `grep -q "## 6. Add \`get_param_grid()\`" src/shared/strategies/TEMPLATE/README.md` — passed (no "Optional" string)

All must-haves confirmed:
- Old strategy folders no longer exist
- TEMPLATE config.py contains complete `get_param_grid()` with correct signature and docstring
- TEMPLATE README section 6 emphasizes param grid as required, not optional

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `! test -d src/shared/strategies/S1` | 0 | ✅ pass | <1s |
| 2 | `! test -d src/shared/strategies/S2` | 0 | ✅ pass | <1s |
| 3 | `grep -q "def get_param_grid" src/shared/strategies/TEMPLATE/config.py` | 0 | ✅ pass | <1s |
| 4 | `grep -q "## 6. Add \`get_param_grid()\`" src/shared/strategies/TEMPLATE/README.md` | 0 | ✅ pass | <1s |

## Diagnostics

**Inspection surfaces for this task:**

- **Directory structure**: `ls src/shared/strategies/` shows only TEMPLATE folder (S1 and S2 absent)
- **Function check**: `grep "def get_param_grid" src/shared/strategies/TEMPLATE/config.py` shows complete function with docstring
- **README content**: Read section 6 of `src/shared/strategies/TEMPLATE/README.md` to verify param grid requirement language
- **Manual verification**: Import TEMPLATE config in Python and check for `get_param_grid` attribute

**Failure states visible via:**
- Missing directories would show in `ls` output
- Missing function would fail grep check and raise `AttributeError` on import
- README regression would show "(Optional)" in section 6 title

## Deviations

None — task plan executed exactly as written.

## Known Issues

None.

## Files Created/Modified

- `src/shared/strategies/S1/` — deleted (old spike reversion strategy)
- `src/shared/strategies/S2/` — deleted (old volatility strategy)
- `src/shared/strategies/TEMPLATE/config.py` — added `get_param_grid()` function with complete docstring
- `src/shared/strategies/TEMPLATE/README.md` — updated section 6 to make param grid non-optional
