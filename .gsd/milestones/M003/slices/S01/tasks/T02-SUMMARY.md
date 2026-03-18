---
id: T02
parent: S01
milestone: M003
provides:
  - 7 new strategy folders (S1-S7) with correct class names and stub implementations
  - Strategy naming map applied (S1_calibration, S2_momentum, S3_reversion, S4_volatility, S5_time_phase, S6_streak, S7_composite)
  - Registry discovers all 8 strategies (TEMPLATE + 7 new)
  - Each strategy instantiates correctly with proper IDs and returns None from evaluate()
key_files:
  - src/shared/strategies/S1/config.py
  - src/shared/strategies/S1/strategy.py
  - src/shared/strategies/S2/config.py
  - src/shared/strategies/S2/strategy.py
  - src/shared/strategies/S3/config.py
  - src/shared/strategies/S3/strategy.py
  - src/shared/strategies/S4/config.py
  - src/shared/strategies/S4/strategy.py
  - src/shared/strategies/S5/config.py
  - src/shared/strategies/S5/strategy.py
  - src/shared/strategies/S6/config.py
  - src/shared/strategies/S6/strategy.py
  - src/shared/strategies/S7/config.py
  - src/shared/strategies/S7/strategy.py
  - scripts/verify_s01_scaffolding.sh
  - scripts/create_strategies.py
key_decisions: []
patterns_established:
  - All strategies follow S{N}Config / S{N}Strategy naming convention
  - Each strategy has TODO comments marking S03 implementation points
  - get_param_grid() returns empty dict {} with TODO comment
  - evaluate() returns None with TODO comment
observability_surfaces:
  - Registry discovery count via discover_strategies() (8 strategies)
  - Strategy metadata via get_strategy('SN').config.strategy_id and strategy_name
  - Stub behavior visible via evaluate() returning None
  - Verification script scripts/verify_s01_scaffolding.sh runs 8 automated checks
duration: ~4 minutes
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T02: Create 7 new strategy folders from TEMPLATE

**Created 7 research-backed strategy folders (S1-S7) from TEMPLATE with correct naming, class structure, and stub implementations ready for S03 logic implementation.**

## What Happened

Created all 7 strategy folders by copying TEMPLATE and customizing each with strategy-specific naming:
- S1: S1_calibration (Calibration Mispricing)
- S2: S2_momentum (Early Momentum)
- S3: S3_reversion (Mean Reversion)
- S4: S4_volatility (Volatility Regime)
- S5: S5_time_phase (Time-Phase Entry)
- S6: S6_streak (Streak/Sequence)
- S7: S7_composite (Composite Ensemble)

Wrote a Python script (`scripts/create_strategies.py`) to automate the pattern since all 7 follow identical structure. Each strategy folder contains:
- `__init__.py` (empty)
- `config.py` with `S{N}Config` class, correct strategy_id and strategy_name from naming map, and `get_param_grid()` returning `{}` with TODO comment
- `strategy.py` with `S{N}Strategy` class, correct import path, updated docstring with strategy description, and `evaluate()` returning `None` with TODO comment

All class names were correctly updated (no leftover "Template" references in code). README.md files were copied as-is and still contain template documentation, which is expected.

Created `scripts/verify_s01_scaffolding.sh` to implement the slice-level verification checks. The script validates folder structure, registry discovery, instantiation, correct IDs/names, stub behavior, and absence of Template references.

Registry successfully discovers all 8 strategies (TEMPLATE + S1-S7). Each strategy instantiates correctly and returns `None` from `evaluate()`, confirming stub behavior.

## Verification

Ran all verification checks from task plan:
1. All 7 folders exist: `for i in {1..7}; do test -d src/shared/strategies/S$i || exit 1; done` — PASS
2. All have `__init__.py`: `for i in {1..7}; do test -f src/shared/strategies/S$i/__init__.py || exit 1; done` — PASS
3. Strategy class names correct: `for i in {1..7}; do grep -q "class S${i}Strategy" src/shared/strategies/S$i/strategy.py || exit 1; done` — PASS
4. Config class names correct: `for i in {1..7}; do grep -q "class S${i}Config" src/shared/strategies/S$i/config.py || exit 1; done` — PASS
5. No Template references in code: `! grep -r "TemplateStrategy\|TemplateConfig" src/shared/strategies/S[1-7]/*.py` — PASS
6. Naming map applied: `grep "strategy_name" src/shared/strategies/S1/config.py | grep -q "S1_calibration"` — PASS

Ran slice verification script `scripts/verify_s01_scaffolding.sh` which confirms:
- TEMPLATE has `get_param_grid()` function
- All 7 strategy folders exist with required files
- Registry discovers 8 strategies (TEMPLATE + 7 new)
- Each strategy instantiates with correct strategy_id and strategy_name
- All strategies return `None` from `evaluate()` (stub behavior)
- No Template references in Python code

Tested registry discovery and instantiation:
```python
discover_strategies()  # Returns 8 strategies: TEMPLATE, S1-S7
get_strategy('S1')     # Returns S1Strategy with strategy_id="S1", strategy_name="S1_calibration"
get_strategy('S3')     # Returns S3Strategy with strategy_id="S3", strategy_name="S3_reversion"
get_strategy('S7')     # Returns S7Strategy with strategy_id="S7", strategy_name="S7_composite"
```

All strategies' `evaluate()` returns `None` when called with a test MarketSnapshot.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `for i in {1..7}; do test -d src/shared/strategies/S$i \|\| exit 1; done` | 0 | ✅ pass | <1s |
| 2 | `for i in {1..7}; do test -f src/shared/strategies/S$i/__init__.py \|\| exit 1; done` | 0 | ✅ pass | <1s |
| 3 | `for i in {1..7}; do grep -q "class S\${i}Strategy" src/shared/strategies/S$i/strategy.py \|\| exit 1; done` | 0 | ✅ pass | <1s |
| 4 | `for i in {1..7}; do grep -q "class S\${i}Config" src/shared/strategies/S$i/config.py \|\| exit 1; done` | 0 | ✅ pass | <1s |
| 5 | `! grep -r "TemplateStrategy\|TemplateConfig" src/shared/strategies/S[1-7]/*.py` | 0 | ✅ pass | <1s |
| 6 | `grep "strategy_name" src/shared/strategies/S1/config.py \| grep -q "S1_calibration"` | 0 | ✅ pass | <1s |
| 7 | `bash scripts/verify_s01_scaffolding.sh` | 0 | ✅ pass | ~2s |

## Diagnostics

**Inspection Commands:**
- `ls src/shared/strategies/` — shows 8 folders (TEMPLATE, S1-S7)
- `python -c "from shared.strategies.registry import discover_strategies; print(sorted(discover_strategies().keys()))"` — lists all discovered strategy IDs
- `python -c "from shared.strategies.registry import get_strategy; s = get_strategy('S3'); print(f'{s.config.strategy_id} | {s.config.strategy_name}')"` — verify individual strategy metadata
- `grep -r "class.*Strategy" src/shared/strategies/S[1-7]/ | wc -l` — should output 7 (one class per strategy)
- `scripts/verify_s01_scaffolding.sh` — automated 8-step verification

**Signals:**
- Registry discovery count: `discover_strategies()` returns 8 strategies (was 1 in TEMPLATE-only state)
- Strategy instantiation: `get_strategy('S1')` through `get_strategy('S7')` succeed
- Stub behavior: All `evaluate()` calls return `None` (no signals generated)
- Class name validation: grep finds correct S{N}Strategy and S{N}Config in each folder

**Failure Visibility:**
- Missing folder: registry returns < 8 items, ls count mismatch
- Import error: `get_strategy()` raises ImportError or AttributeError
- Wrong metadata: assertion fails on strategy_id or strategy_name comparison
- Leftover templates: grep finds "TemplateStrategy" or "TemplateConfig" in new files

## Deviations

None. Task plan followed exactly.

## Known Issues

None. All 7 strategies created successfully and pass all verification checks.

## Files Created/Modified

- `src/shared/strategies/S1/__init__.py` — empty file for package structure
- `src/shared/strategies/S1/config.py` — S1Config with strategy_id="S1", strategy_name="S1_calibration", stub get_param_grid()
- `src/shared/strategies/S1/strategy.py` — S1Strategy with stub evaluate() returning None
- `src/shared/strategies/S1/README.md` — copied TEMPLATE documentation
- `src/shared/strategies/S2/__init__.py` — empty file for package structure
- `src/shared/strategies/S2/config.py` — S2Config with strategy_id="S2", strategy_name="S2_momentum", stub get_param_grid()
- `src/shared/strategies/S2/strategy.py` — S2Strategy with stub evaluate() returning None
- `src/shared/strategies/S2/README.md` — copied TEMPLATE documentation
- `src/shared/strategies/S3/__init__.py` — empty file for package structure
- `src/shared/strategies/S3/config.py` — S3Config with strategy_id="S3", strategy_name="S3_reversion", stub get_param_grid()
- `src/shared/strategies/S3/strategy.py` — S3Strategy with stub evaluate() returning None
- `src/shared/strategies/S3/README.md` — copied TEMPLATE documentation
- `src/shared/strategies/S4/__init__.py` — empty file for package structure
- `src/shared/strategies/S4/config.py` — S4Config with strategy_id="S4", strategy_name="S4_volatility", stub get_param_grid()
- `src/shared/strategies/S4/strategy.py` — S4Strategy with stub evaluate() returning None
- `src/shared/strategies/S4/README.md` — copied TEMPLATE documentation
- `src/shared/strategies/S5/__init__.py` — empty file for package structure
- `src/shared/strategies/S5/config.py` — S5Config with strategy_id="S5", strategy_name="S5_time_phase", stub get_param_grid()
- `src/shared/strategies/S5/strategy.py` — S5Strategy with stub evaluate() returning None
- `src/shared/strategies/S5/README.md` — copied TEMPLATE documentation
- `src/shared/strategies/S6/__init__.py` — empty file for package structure
- `src/shared/strategies/S6/config.py` — S6Config with strategy_id="S6", strategy_name="S6_streak", stub get_param_grid()
- `src/shared/strategies/S6/strategy.py` — S6Strategy with stub evaluate() returning None
- `src/shared/strategies/S6/README.md` — copied TEMPLATE documentation
- `src/shared/strategies/S7/__init__.py` — empty file for package structure
- `src/shared/strategies/S7/config.py` — S7Config with strategy_id="S7", strategy_name="S7_composite", stub get_param_grid()
- `src/shared/strategies/S7/strategy.py` — S7Strategy with stub evaluate() returning None
- `src/shared/strategies/S7/README.md` — copied TEMPLATE documentation
- `scripts/create_strategies.py` — automation script to create all 7 strategies from TEMPLATE
- `scripts/verify_s01_scaffolding.sh` — slice-level verification script for S01
