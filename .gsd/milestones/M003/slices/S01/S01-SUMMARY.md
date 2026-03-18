---
id: S01
parent: M003
milestone: M003
provides:
  - 7 new strategy folders (S1-S7) with research-backed naming and correct stub structure
  - Updated TEMPLATE with get_param_grid() function and param grid requirement documentation
  - Registry auto-discovery of all 8 strategies (TEMPLATE + S1-S7)
  - Verified instantiation with correct strategy IDs and names from naming map
  - All evaluate() methods return None (stub behavior) ready for S03 implementation
requires:
  - slice: none
    provides: standalone scaffolding slice
affects:
  - S03 (will implement real evaluate() logic in all 7 strategies)
key_files:
  - src/shared/strategies/TEMPLATE/config.py
  - src/shared/strategies/TEMPLATE/README.md
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
  - get_param_grid() is required for all strategies, returns {} with TODO during scaffolding
  - evaluate() returns None with TODO comment until S03 implements real logic
  - Verification script consolidates all slice-level checks with embedded Python for complex registry/instantiation tests
observability_surfaces:
  - Registry discovery via discover_strategies() returns 8 strategy IDs
  - Instantiation metadata via get_strategy('SN').config attributes
  - Verification script scripts/verify_s01_scaffolding.sh with structured PASS/FAIL output
drill_down_paths:
  - .gsd/milestones/M003/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M003/slices/S01/tasks/T02-SUMMARY.md
  - .gsd/milestones/M003/slices/S01/tasks/T03-SUMMARY.md
duration: 20m
verification_result: passed
completed_at: 2026-03-18T13:58:36+01:00
---

# S01: Clean slate + strategy scaffolding

**Replaced disposable proof-of-concept strategies with scaffolding for 7 research-backed strategies; registry discovers all strategies with correct IDs, names, and stub implementations ready for S03.**

## What Happened

Executed a clean-slate operation to prepare for M003's research-backed strategy suite:

**T01: Delete old strategies and update TEMPLATE (4m)**
- Deleted old `S1/` (spike reversion) and `S2/` (volatility) strategy folders entirely
- Added `get_param_grid()` skeleton to `TEMPLATE/config.py` with comprehensive docstring explaining grid-search usage, example patterns, and return contract
- Updated `TEMPLATE/README.md` section 6 to remove "(Optional)" from param grid section and make it a required component
- Established param grid as first-class requirement for all new strategies

**T02: Create 7 new strategy folders from TEMPLATE (4m)**
- Created 7 strategy folders by copying TEMPLATE and applying the naming map:
  - S1: S1_calibration (Calibration Mispricing)
  - S2: S2_momentum (Early Momentum)
  - S3: S3_reversion (Mean Reversion)
  - S4: S4_volatility (Volatility Regime)
  - S5: S5_time_phase (Time-Phase Entry)
  - S6: S6_streak (Streak/Sequence)
  - S7: S7_composite (Composite Ensemble)
- Wrote automation script `scripts/create_strategies.py` to handle repetitive folder setup
- Each strategy folder contains:
  - `__init__.py` (empty package marker)
  - `config.py` with `S{N}Config` class, correct strategy_id and strategy_name, and `get_param_grid()` returning `{}` with TODO
  - `strategy.py` with `S{N}Strategy` class, correct import paths, updated docstrings, and `evaluate()` returning `None` with TODO
  - `README.md` (copied TEMPLATE documentation)
- All class names correctly updated with no leftover "Template" references in code

**T03: Write verification script and prove registry discovery (12m)**
- Created comprehensive verification script `scripts/verify_s01_scaffolding.sh` with 6 check groups covering 25 individual validations
- Script uses embedded Python for complex checks (registry discovery, instantiation, evaluation) to avoid bash portability issues
- Verification proves:
  - Old S1/S2 replaced with new structure using research-backed names
  - TEMPLATE has callable `get_param_grid()` function
  - All 7 folders exist with required files
  - Registry discovers 8 strategies (S1-S7 + TEMPLATE)
  - All strategies instantiate with correct metadata (strategy_id, strategy_name)
  - All evaluate() calls return None (stub behavior)
- Script ran successfully with all 25 checks passing

Registry successfully discovers all 8 strategies and returns them in a dict keyed by strategy ID. Each strategy can be instantiated via `get_strategy('S1')` through `get_strategy('S7')` and has correct metadata attributes. All evaluate() methods return None as expected for stub implementations.

## Verification

**Slice-level verification (scripts/verify_s01_scaffolding.sh):**
- ✓ 25 checks passed, 0 failed
- ✓ Registry discovered all 8 strategies: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'TEMPLATE']
- ✓ All strategies instantiated with correct IDs and names matching naming map
- ✓ All evaluate() calls returned None (stub behavior confirmed)
- ✓ No Template references found in new strategy Python files

**Task-level verification:**
- T01: Old S1/S2 folders deleted, TEMPLATE has `get_param_grid()`, README section 6 updated
- T02: All 7 folders exist with required files, class names correct, no Template references in code
- T03: Verification script runs without errors and proves all must-haves

**Manual spot-check:**
```python
from shared.strategies.registry import discover_strategies, get_strategy
strategies = discover_strategies()
# Returns: {'S1': <module>, 'S2': <module>, ..., 'S7': <module>, 'TEMPLATE': <module>}

s1 = get_strategy('S1')
# s1.config.strategy_id == 'S1'
# s1.config.strategy_name == 'S1_calibration'
# s1.evaluate(market_snapshot) returns None
```

## Requirements Advanced

- **R002** — S01 established 7 new strategy folders in `shared/strategies/` replacing old S1/S2; structure verified via registry discovery
- **R008** — Registry discovers all 7 new strategies by scanning folders; proven by verification script check 4
- **R011** — TEMPLATE updated with `get_param_grid()` function and param grid requirement documentation; proven by verification script check 2
- **R014** — Each of 7 strategies is self-contained folder with config, evaluate(), and param grid stub; proven by verification script checks 3-6
- **R015** — Old S1/S2 deleted and TEMPLATE updated; proven by verification script check 1

## Requirements Validated

None — S01 advances scaffolding but does not validate end-to-end requirements. Validation requires S02 (engine upgrades) and S03 (real implementations).

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None — task plan executed exactly as written.

## Known Limitations

- All 7 strategies have stub implementations only — `evaluate()` returns None and generates no signals
- `get_param_grid()` returns empty dict `{}` for all strategies — parameter ranges will be defined in S03
- README.md files in new strategy folders still contain generic TEMPLATE documentation — strategy-specific docs will be written in S03
- No backtest output yet — strategies need real implementations before `backtest_strategies.py` can produce results

## Follow-ups

- S02 must implement dynamic fee formula and configurable slippage in engine before strategies can be tested with realistic trading costs
- S03 must implement real `evaluate()` logic for all 7 strategies with meaningful `get_param_grid()` parameter ranges
- Strategy README.md files should be updated with strategy-specific documentation when logic is implemented in S03

## Files Created/Modified

- `src/shared/strategies/S1/` — deleted (old spike reversion), then recreated with S1_calibration scaffolding
- `src/shared/strategies/S2/` — deleted (old volatility), then recreated with S2_momentum scaffolding
- `src/shared/strategies/S3/` — created with S3_reversion scaffolding
- `src/shared/strategies/S4/` — created with S4_volatility scaffolding
- `src/shared/strategies/S5/` — created with S5_time_phase scaffolding
- `src/shared/strategies/S6/` — created with S6_streak scaffolding
- `src/shared/strategies/S7/` — created with S7_composite scaffolding
- `src/shared/strategies/TEMPLATE/config.py` — added `get_param_grid()` function with full docstring
- `src/shared/strategies/TEMPLATE/README.md` — updated section 6 to make param grid non-optional
- `scripts/create_strategies.py` — automation script to create all 7 strategies from TEMPLATE
- `scripts/verify_s01_scaffolding.sh` — comprehensive slice verification script with 25 checks

Each new strategy folder (S1-S7) contains:
- `__init__.py` — empty package marker
- `config.py` — `S{N}Config` class with correct strategy_id, strategy_name, and stub `get_param_grid()`
- `strategy.py` — `S{N}Strategy` class with stub `evaluate()` returning None
- `README.md` — TEMPLATE documentation (to be updated in S03)

## Forward Intelligence

### What the next slice should know

- **Registry auto-discovery works reliably** — Just add a folder with the right structure and it's automatically discovered. No hardcoded imports needed.
- **Naming convention is rigid** — S{N}Config and S{N}Strategy class names are expected by the registry. Deviation breaks discovery.
- **Stub implementations are clean** — All evaluate() methods return None consistently. S03 can replace them without worrying about partial implementations.
- **Verification script is comprehensive** — `scripts/verify_s01_scaffolding.sh` covers all critical checks. S03 can extend it or build a similar pattern for post-implementation verification.
- **Parameter grid structure established** — TEMPLATE shows the expected return format and documentation pattern. S03 should follow the same pattern for consistency.

### What's fragile

- **Import paths are absolute** — Each strategy.py imports `from shared.strategies.S{N}.config import S{N}Config`. If folder structure changes, all imports break. This is by design for explicitness but means refactoring folder structure requires coordinated updates.
- **README.md files are stale** — All new strategy folders have generic TEMPLATE documentation. If someone tries to use a README before S03 updates them, they'll get misleading guidance.
- **No parameter validation yet** — `get_param_grid()` returns {} stubs. If someone accidentally calls the optimizer before S03 implements real grids, it will succeed with empty grid (running once with default config). This is correct behavior but might be surprising.

### Authoritative diagnostics

- **Registry discovery is the primary health signal** — If `discover_strategies()` returns 8 strategies, the scaffolding is working. Any fewer means a folder is missing or broken.
- **Verification script is the single source of truth** — `bash scripts/verify_s01_scaffolding.sh` exit code 0 means S01 is complete and correct. Exit 1 means something broke. Trust this over manual inspection.
- **Instantiation metadata is the correctness check** — `get_strategy('S1').config.strategy_name == 'S1_calibration'` proves the naming map was applied correctly. This is how S03 should verify it didn't break anything.

### What assumptions changed

- **Python automation preferred over manual copying** — Initial plan suggested manual folder copying with pattern substitution. Task execution revealed this was error-prone with 7 strategies, so `scripts/create_strategies.py` was written instead. This pattern should be reused if more strategies are added in the future.
- **Embedded Python in verification script** — Originally planned as pure bash, but bash associative array portability (macOS uses bash 3.x) made Python heredoc approach more reliable. This pattern works well for complex verification.
